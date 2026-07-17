import asyncio
import datetime
import logging
import os
import re
from typing import Any

from .audio_transcribe import Audio_agent
from .db_client import ensure_events_indexes, get_events_collection
from .memory_schema import memory_event_from_mongo, memory_event_to_mongo, new_memory_event
from .media_paths import normalize_stored_path, to_fs_path, to_stored_path
from .semantic_search import index_memory_event
from .safety_agent import assess_event_safety, empty_safety_assessment
from .alert_service import create_alert_for_safety_assessment
from .timezone_utils import now_local
from .video_agent import Video_Agent, video_results

# So video is recorded. Then it is passed to the consolidator agent.
# The consolidator agent will call the video_agent, to describe the video, and the audio_agent which will then transcribe the audio
# After the video description and audio transcript has been received, we will create a state object which will contain the following:
# 1. Unique ascending ID
# 2. Time and Date of recording
# 3. Room Number
# 4. Video Description
# 5. Audio Transcript
# 6. Last screenshot
# 7. Video Path

# This state object will be stored in a NoSQL database. Which will then be interacted with the jeeves agent (main agent)


logger = logging.getLogger(__name__)


def _path_variants(path: str) -> list[Any]:
    if not path:
        return []
    variants = [path, os.path.normpath(path)]
    try:
        variants.append(os.path.abspath(path))
    except OSError:
        pass
    stored = normalize_stored_path(path)
    if stored:
        variants.extend([stored, os.path.normpath(stored)])
        separator_tolerant_suffix = r"[\\/]".join(
            re.escape(part) for part in stored.split("/")
        )
        variants.append(
            re.compile(rf"(?:^|.*[\\/]){separator_tolerant_suffix}$", re.IGNORECASE)
        )
    return list(dict.fromkeys(variants))


def _filesystem_argument(path: str) -> str:
    resolved = to_fs_path(path)
    return str(resolved) if resolved is not None else ""


def _brief_failure_note(modality: str) -> str:
    return f"{modality} unavailable for this recording."


async def consolidator_agent(
    video_path: str,
    audio_path: str,
    screenshot_path: str,
    room_number: int,
    timestamp: datetime.datetime = None,
    mongo_connection_string: str = None,
):
    if timestamp is None:
        timestamp = now_local()

    if mongo_connection_string:
        logger.warning(
            "consolidator_agent ignores mongo_connection_string and uses shared db_client settings."
        )

    await ensure_events_indexes()
    collection = get_events_collection()
    existing_doc = await collection.find_one({"video_path": {"$in": _path_variants(video_path)}})
    if existing_doc:
        existing_event = memory_event_from_mongo(existing_doc)
        try:
            await index_memory_event(existing_event)
        except Exception as exc:
            logger.warning(
                "Duplicate event %s found but semantic re-index failed: %s",
                existing_event.event_id,
                exc,
            )
        return existing_doc.get("_id") or existing_event.event_id

    # Run video description and audio transcription in parallel (independent tasks)
    video_agent = Video_Agent()
    audio_agent = Audio_agent()
    loop = asyncio.get_running_loop()

    video_result, audio_result = await asyncio.gather(
        loop.run_in_executor(
            None, video_agent.video_description, _filesystem_argument(video_path)
        ),
        loop.run_in_executor(
            None, audio_agent.transcribe_audio, _filesystem_argument(audio_path)
        ),
        return_exceptions=True,
    )

    if isinstance(video_result, Exception):
        logger.warning("Video description failed for %s: %s", video_path, video_result)
        video_details = video_results(
            video_description=_brief_failure_note("Video analysis"),
            room_objects=[],
        )
    else:
        video_details = video_result

    if isinstance(audio_result, Exception):
        logger.warning("Audio transcription failed for %s: %s", audio_path, audio_result)
        audio_transcript = _brief_failure_note("Audio transcription")
    else:
        audio_transcript = str(audio_result or "")

    # we will now create a JSON object which is going to be stored in the database

    event = new_memory_event(
        timestamp=timestamp,
        room_number=room_number,
        video_description=video_details.video_description,
        room_objects=video_details.room_objects,
        audio_transcript=audio_transcript,
        screenshot_path=to_stored_path(screenshot_path) or "",
        video_path=to_stored_path(video_path) or "",
        audio_path=to_stored_path(audio_path) or "",
        danger_candidate=video_details.danger_candidate,
        scene_end_state=video_details.scene_end_state,
        observed_hazards=video_details.observed_hazards,
        uncertainties=video_details.uncertainties,
    )

    try:
        safety_assessment = await assess_event_safety(event)
    except Exception as exc:
        logger.warning(
            "Safety assessment failed for event %s but ingestion will continue: %s",
            event.event_id,
            exc,
        )
        safety_assessment = empty_safety_assessment(
            f"Safety assessment failed: {exc}"
        )
    event.safety_assessment = safety_assessment.model_dump(mode="json")

    document = memory_event_to_mongo(event)
    result = await collection.insert_one(document)
    print(f"Inserted document with ID: {result.inserted_id}")

    try:
        await create_alert_for_safety_assessment(event, safety_assessment)
    except Exception as exc:
        logger.warning(
            "Safety alert creation failed for event %s but ingestion will continue: %s",
            event.event_id,
            exc,
        )

    try:
        await index_memory_event(event)
    except Exception as exc:
        logger.warning(
            "Mongo write succeeded but semantic indexing failed for event %s: %s",
            event.event_id,
            exc,
        )
    return result.inserted_id
