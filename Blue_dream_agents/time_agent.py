from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

PATIENT_SAFE_ERROR_MESSAGE = (
    "I'm having a little trouble remembering right now. "
    "Please try again in a moment."
)

try:
    from .db_client import get_mongo_client, close_mongo_client
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from .llm.client import invoke_structured, invoke_text
    from .memory_schema import (
        MemoryEvent,
        ROOMS,
        ROOM_NAME_TO_ID,
        memory_event_from_mongo,
        normalize_timestamp,
    )
    from .prompt_budget import compact_json_records, truncate_text
    from .timezone_utils import LOCAL_TZ, now_local
except ImportError:
    from db_client import get_mongo_client, close_mongo_client
    from llm.model_registry import get_model_registry
    from llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from llm.client import invoke_structured, invoke_text
    from memory_schema import (
        MemoryEvent,
        ROOMS,
        ROOM_NAME_TO_ID,
        memory_event_from_mongo,
        normalize_timestamp,
    )
    from prompt_budget import compact_json_records, truncate_text
    from timezone_utils import LOCAL_TZ, now_local


class TimelineResult(BaseModel):
    success: bool = Field(description="Whether events were found")
    event_count: int = Field(description="Number of events found")
    time_range: str = Field(description="Human-readable time range queried")
    summary: str = Field(description="Digestible narrative of activities")


class TranscriptResult(BaseModel):
    success: bool = Field(description="Whether transcripts were found")
    transcript_count: int = Field(description="Number of transcripts found")
    time_range: str = Field(description="Human-readable time range queried")
    transcripts: List[str] = Field(default_factory=list)
    summary: str = Field(description="Summary of what was discussed")


class ActivityCheckResult(BaseModel):
    found: bool = Field(description="Whether the activity was found")
    keyword: str = Field(description="What was searched for")
    confidence: str = Field(description="Confidence level: high, medium, low")
    summary: str = Field(description="Summary of findings")


class TimeWindowContext(BaseModel):
    success: bool = False
    event_count: int = 0
    time_range: str = ""
    room_name: Optional[str] = None
    summary: str = ""
    transcripts: List[str] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)


class TimeResult(BaseModel):
    response_type: Literal["timeline", "transcripts", "activity_check", "general"] = (
        "general"
    )
    text: str = Field(description="The main human-readable answer to display")
    data: Dict[str, Any] = Field(default_factory=dict, description="Raw structured data")


class TimeQueryPlan(BaseModel):
    intent: Literal["timeline", "transcripts", "activity_check", "general"] = (
        "general"
    )
    time_range: str = "today"
    room_name: Optional[str] = None
    activity: Optional[str] = None
    hours: int = 24


class ActivityEvidence(BaseModel):
    found: bool = False
    confidence: Literal["high", "medium", "low"] = "low"
    evidence: str = ""


_SPEECH_RECALL_TERMS = (
    "talk",
    "talking",
    "said",
    "say",
    "saying",
    "discuss",
    "discussed",
    "discussing",
    "mention",
    "mentioned",
    "mentioning",
    "conversation",
    "transcript",
)
SUMMARY_EVENT_BUDGET_CHARS = 18000
TRANSCRIPT_PROMPT_BUDGET_CHARS = 18000
ACTIVITY_PROMPT_BUDGET_CHARS = 18000


async def close_clients():
    """Legacy convenience wrapper - delegates to shared db_client."""
    await close_mongo_client()


def _parse_room_name(room_name: str) -> Optional[int]:
    room_lower = room_name.lower().strip()
    if room_lower in ROOM_NAME_TO_ID:
        return ROOM_NAME_TO_ID[room_lower]

    for name, room_id in ROOM_NAME_TO_ID.items():
        if room_lower in name or name in room_lower:
            return room_id

    try:
        return int(room_name)
    except ValueError:
        return None


def _build_time_filter(
    time_range: str,
) -> tuple[datetime.datetime, datetime.datetime, str]:
    now = now_local()
    time_range_lower = time_range.lower().strip()

    if time_range_lower == "yesterday":
        start = datetime.datetime.combine(
            now.date() - timedelta(days=1), datetime.time.min, tzinfo=LOCAL_TZ
        )
        end = datetime.datetime.combine(
            now.date() - timedelta(days=1), datetime.time.max, tzinfo=LOCAL_TZ
        )
        desc = "yesterday"
    elif time_range_lower == "today":
        start = datetime.datetime.combine(
            now.date(), datetime.time.min, tzinfo=LOCAL_TZ
        )
        end = now
        desc = "today"
    elif time_range_lower in ("recently", "recent"):
        start = now - timedelta(hours=3)
        end = now
        desc = "the last 3 hours"
    elif "hour" in time_range_lower:
        match = re.search(r"(\d+)", time_range_lower)
        hours = int(match.group(1)) if match else 3
        start = now - timedelta(hours=hours)
        end = now
        desc = f"the last {hours} hour{'s' if hours != 1 else ''}"
    elif "day" in time_range_lower:
        match = re.search(r"(\d+)", time_range_lower)
        days = int(match.group(1)) if match else 1
        start = now - timedelta(days=days)
        end = now
        desc = f"the last {days} day{'s' if days != 1 else ''}"
    else:
        parsed_date: Optional[datetime.datetime] = None
        for date_format in ("%Y-%m-%d", "%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y"):
            try:
                parsed_date = datetime.datetime.strptime(time_range, date_format)
                break
            except ValueError:
                continue

        if parsed_date is not None:
            start = datetime.datetime.combine(
                parsed_date.date(), datetime.time.min, tzinfo=LOCAL_TZ
            )
            end = datetime.datetime.combine(
                parsed_date.date(), datetime.time.max, tzinfo=LOCAL_TZ
            )
            desc = parsed_date.strftime("%B %d, %Y")
        else:
            start = datetime.datetime.combine(
                now.date(), datetime.time.min, tzinfo=LOCAL_TZ
            )
            end = now
            desc = "today"

    return start, end, desc


def _extract_time_range_from_query(query: str) -> str:
    query_lower = query.lower()
    if "yesterday" in query_lower:
        return "yesterday"
    if "today" in query_lower or "tonight" in query_lower:
        return "today"
    if "earlier" in query_lower or "recent" in query_lower:
        return "recently"

    hour_match = re.search(r"(?:last|past)\s+(\d+)\s+hours?", query_lower)
    if hour_match:
        return f"last {hour_match.group(1)} hours"

    day_match = re.search(r"(?:last|past)\s+(\d+)\s+days?", query_lower)
    if day_match:
        return f"last {day_match.group(1)} days"

    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)
    if iso_match:
        return iso_match.group(0)

    natural_date_match = re.search(
        r"\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|"
        r"Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|"
        r"Dec|December)\s+\d{1,2},?\s+\d{4}\b",
        query,
        flags=re.IGNORECASE,
    )
    if natural_date_match:
        return natural_date_match.group(0)

    return "today"


def _looks_like_speech_recall(query: str) -> bool:
    query_lower = query.lower()
    return any(term in query_lower for term in _SPEECH_RECALL_TERMS)


def _deterministic_time_plan(query: str) -> Optional[TimeQueryPlan]:
    if _looks_like_speech_recall(query):
        return TimeQueryPlan(
            intent="transcripts",
            time_range=_extract_time_range_from_query(query),
            room_name=None,
            activity=None,
            hours=24,
        )
    return None


async def _get_events(
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    room_number: Optional[int] = None,
    limit: int = 100,
) -> List[MemoryEvent]:
    collection = get_mongo_client().dementia_assistance.events
    query: Dict[str, Any] = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}
    if room_number is not None:
        query["room_number"] = room_number

    events: List[MemoryEvent] = []
    cursor = collection.find(query).sort("timestamp", 1).limit(limit)
    async for doc in cursor:
        events.append(memory_event_from_mongo(doc))

    return events


async def _summarize_with_llm(
    events: List[MemoryEvent], user_query_context: str
) -> str:
    if not events:
        return "I couldn't find any recorded activities for that time."

    context_data = []
    for event in events:
        context_data.append(
            {
                "time": event.timestamp.strftime("%I:%M %p"),
                "room": event.room_name,
                "activity": truncate_text(event.video_description, 900),
                "speech": truncate_text(event.audio_transcript, 700),
            }
        )
    context_data = compact_json_records(
        context_data,
        max_chars=SUMMARY_EVENT_BUDGET_CHARS,
    )

    registry = get_model_registry()
    prompt = with_monitoring_evidence_context(
        f'Question: "{user_query_context}"\n'
        f"Event log:\n{json.dumps(context_data, indent=2)}\n\n"
        "Respond in 2-3 short sentences. Be warm, clear, and mention specific "
        "times or rooms when useful."
    )
    return await invoke_text(
        prompt=prompt,
        system_prompt=with_patient_answer_context(
            "You are a compassionate memory assistant helping a dementia patient "
            "recall recent activity. Convert third-person monitoring descriptions "
            "into direct second-person phrasing."
        ),
        model_id=registry.synthesis,
        max_tokens=500,
    )


async def get_time_window_context(
    anchor_timestamp: datetime.datetime | str,
    *,
    query: str,
    room_name: Optional[str] = None,
    window_minutes: int = 20,
    limit: int = 40,
) -> TimeWindowContext:
    try:
        anchor_dt = normalize_timestamp(anchor_timestamp)
        room_id = _parse_room_name(room_name) if room_name else None
        start_dt = anchor_dt - timedelta(minutes=window_minutes)
        end_dt = anchor_dt + timedelta(minutes=window_minutes)
        events = await _get_events(start_dt, end_dt, room_number=room_id, limit=limit)
        time_range = (
            f"{start_dt.strftime('%b %d %I:%M %p')} to "
            f"{end_dt.strftime('%b %d %I:%M %p')}"
        )
        if not events:
            return TimeWindowContext(
                success=False,
                event_count=0,
                time_range=time_range,
                room_name=room_name,
                summary="I couldn't find nearby events to further ground that memory.",
                transcripts=[],
                events=[],
            )

        transcripts = [
            f"[{event.timestamp.strftime('%I:%M %p')} - {event.room_name}] "
            f"{event.audio_transcript}"
            for event in events
            if event.audio_transcript.strip()
        ]
        summary = await _summarize_with_llm(
            events,
            (
                f'Question: "{query}"\n'
                "Use the nearby events to verify and ground the memory around the "
                f"anchor time range {time_range}."
            ),
        )
        serialized_events = [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "room_name": event.room_name,
                "video_description": event.video_description,
                "audio_transcript": event.audio_transcript,
            }
            for event in events
        ]
        return TimeWindowContext(
            success=True,
            event_count=len(events),
            time_range=time_range,
            room_name=room_name or (events[0].room_name if events else None),
            summary=summary,
            transcripts=transcripts,
            events=serialized_events,
        )
    except Exception as exc:
        logger.exception("Nearby time-window lookup failed")
        return TimeWindowContext(
            success=False,
            event_count=0,
            time_range="",
            room_name=room_name,
            summary=PATIENT_SAFE_ERROR_MESSAGE,
            transcripts=[],
            events=[],
        )


async def get_activity_history(time_range: str) -> TimelineResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        events = await _get_events(start_dt, end_dt)
        if not events:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_desc,
                summary=f"I don't have any recorded activities for {time_desc}. "
                "This might mean the cameras weren't active or you were away.",
            )

        summary = await _summarize_with_llm(events, f"What was I doing {time_desc}?")
        return TimelineResult(
            success=True,
            event_count=len(events),
            time_range=time_desc,
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Activity-history lookup failed")
        return TimelineResult(
            success=False,
            event_count=0,
            time_range=time_range,
            summary=PATIENT_SAFE_ERROR_MESSAGE,
        )


async def get_room_activity(
    room_name: str, time_range: str = "today"
) -> TimelineResult:
    try:
        room_id = _parse_room_name(room_name)
        if room_id is None:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_range,
                summary=f"I'm sorry, I don't recognize the room '{room_name}'. "
                f"I currently monitor: {', '.join(ROOM_NAME_TO_ID.keys())}.",
            )

        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        events = await _get_events(start_dt, end_dt, room_number=room_id)
        clean_room_name = ROOMS.get(room_id, room_name)
        if not events:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_desc,
                summary=(
                    f"I didn't see any activity in the {clean_room_name} during "
                    f"{time_desc}."
                ),
            )

        summary = await _summarize_with_llm(
            events, f"What was I doing in the {clean_room_name} during {time_desc}?"
        )
        return TimelineResult(
            success=True,
            event_count=len(events),
            time_range=time_desc,
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Room-activity lookup failed")
        return TimelineResult(
            success=False,
            event_count=0,
            time_range=time_range,
            summary=PATIENT_SAFE_ERROR_MESSAGE,
        )


async def get_recent_transcripts(
    time_range: str = "recently", room_name: Optional[str] = None
) -> TranscriptResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        room_id = _parse_room_name(room_name) if room_name else None
        room_display = ""

        if room_name:
            if room_id is None:
                return TranscriptResult(
                    success=False,
                    transcript_count=0,
                    time_range=time_desc,
                    transcripts=[],
                    summary=f"I'm sorry, I don't recognize the room '{room_name}'. "
                    f"I currently monitor: {', '.join(ROOM_NAME_TO_ID.keys())}.",
                )
            room_display = f" in the {ROOMS.get(room_id, room_name)}"

        events = await _get_events(start_dt, end_dt, room_number=room_id)
        speech_events = [
            event
            for event in events
            if event.audio_transcript and len(event.audio_transcript.strip()) > 5
        ]
        if not speech_events:
            return TranscriptResult(
                success=False,
                transcript_count=0,
                time_range=time_desc,
                transcripts=[],
                summary=f"I didn't capture any conversations{room_display} during {time_desc}. "
                "Perhaps you were quiet or away from the microphones.",
            )

        transcripts = [
            f"[{event.timestamp.strftime('%I:%M %p')} - {event.room_name}] "
            f"{truncate_text(event.audio_transcript, 900)}"
            for event in speech_events
        ]
        budgeted_transcripts: list[str] = []
        total_chars = 0
        for transcript in transcripts:
            if total_chars + len(transcript) > TRANSCRIPT_PROMPT_BUDGET_CHARS:
                break
            budgeted_transcripts.append(transcript)
            total_chars += len(transcript)
        transcripts = budgeted_transcripts
        registry = get_model_registry()
        prompt = with_monitoring_evidence_context(
            f"Transcripts from {time_desc}{room_display}:\n"
            + "\n".join(f"- {entry}" for entry in transcripts)
            + "\n\nSummarize the main topics kindly and clearly in 2-3 sentences."
        )
        summary = await invoke_text(
            prompt=prompt,
            system_prompt=with_patient_answer_context(
                "You help a dementia patient remember what they were talking about. "
                "Be warm, concise, and grounded in the transcript. Prefer the actual "
                "audio transcript over video descriptions for speech questions."
            ),
            model_id=registry.synthesis,
            max_tokens=500,
        )
        return TranscriptResult(
            success=True,
            transcript_count=len(transcripts),
            time_range=time_desc,
            transcripts=transcripts,
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Transcript lookup failed")
        return TranscriptResult(
            success=False,
            transcript_count=0,
            time_range=time_range,
            transcripts=[],
            summary=PATIENT_SAFE_ERROR_MESSAGE,
        )


async def check_activity(activity: str, hours: int = 24) -> ActivityCheckResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(f"last {hours} hours")
        events = await _get_events(start_dt, end_dt)
        if not events:
            return ActivityCheckResult(
                found=False,
                keyword=activity,
                confidence="low",
                summary=f"I don't have any recorded activities in {time_desc} "
                f"to check for '{activity}'.",
            )

        descriptions = []
        for event in events:
            if event.video_description or event.audio_transcript:
                description_text = (
                    f"{truncate_text(event.video_description, 800)} "
                    f"{truncate_text(event.audio_transcript, 600)}"
                ).strip()
                descriptions.append(
                    f"[{event.timestamp.strftime('%I:%M %p')}] {event.room_name}: "
                    f"{description_text}"
                )
        budgeted_descriptions: list[str] = []
        total_chars = 0
        for description in descriptions:
            if total_chars + len(description) > ACTIVITY_PROMPT_BUDGET_CHARS:
                break
            budgeted_descriptions.append(description)
            total_chars += len(description)
        descriptions = budgeted_descriptions

        if not descriptions:
            return ActivityCheckResult(
                found=False,
                keyword=activity,
                confidence="low",
                summary=f"I have activity records but no detailed descriptions "
                f"to search for '{activity}'.",
            )

        registry = get_model_registry()
        prompt = with_monitoring_evidence_context(
            f'Activity to verify: "{activity}"\n'
            f"Records from {time_desc}:\n"
            + "\n".join(descriptions)
        )
        evidence = await invoke_structured(
            prompt=prompt,
            output_model=ActivityEvidence,
            system_prompt=with_patient_cctv_context(
                "You check whether a dementia patient likely performed a target "
                "activity. Consider synonyms and related phrasing. Return grounded "
                "evidence only. Phrase evidence for patient-facing reuse with 'you' "
                "when referring to the monitored patient."
            ),
            model_id=registry.synthesis,
            structured_output_prompt=(
                "Return whether the activity was found, the confidence level, and "
                "a short evidence string."
            ),
            max_tokens=500,
        )

        if evidence.found:
            if evidence.confidence == "high":
                summary = (
                    f"Yes, I found evidence that you {activity}. {evidence.evidence}"
                )
            else:
                summary = (
                    f"I found possible evidence that you may have {activity}. "
                    f"{evidence.evidence}"
                )
        else:
            summary = (
                f"I didn't find clear evidence of '{activity}' in {time_desc}. "
                "This doesn't mean it didn't happen. I might have missed it, or it "
                "may have happened outside monitored areas."
            )

        return ActivityCheckResult(
            found=evidence.found,
            keyword=activity,
            confidence=evidence.confidence,
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Activity check failed")
        return ActivityCheckResult(
            found=False,
            keyword=activity,
            confidence="low",
            summary=PATIENT_SAFE_ERROR_MESSAGE,
        )


async def _plan_time_query(query: str) -> TimeQueryPlan:
    deterministic_plan = _deterministic_time_plan(query)
    if deterministic_plan is not None:
        return deterministic_plan

    registry = get_model_registry()
    return await invoke_structured(
        prompt=query,
        output_model=TimeQueryPlan,
        system_prompt=with_patient_cctv_context(
            "You route dementia-memory questions into one of four intents: "
            "timeline, transcripts, activity_check, or general. "
            "Timeline is for activity history or room history. "
            "Transcripts is for what was said or discussed. "
            "Activity_check is for verifying whether a specific activity happened."
        ),
        model_id=registry.router,
        structured_output_prompt=(
            "Extract the intent, time range, optional room name, optional activity, "
            "and hours if the user is asking to verify an activity. Use YYYY-MM-DD "
            "for explicit calendar dates. Choose transcripts for questions like "
            "'what was I talking about today', 'what was I saying today', and "
            "'did I talk about X today'."
        ),
        max_tokens=300,
    )


async def run_time_query(query: str) -> TimeResult:
    try:
        plan = await _plan_time_query(query)
        if plan.intent == "transcripts":
            result = await get_recent_transcripts(
                time_range=plan.time_range,
                room_name=plan.room_name,
            )
            return TimeResult(
                response_type="transcripts",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        if plan.intent == "activity_check":
            activity = plan.activity or query
            result = await check_activity(activity=activity, hours=plan.hours)
            return TimeResult(
                response_type="activity_check",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        if plan.intent == "timeline":
            if plan.room_name:
                result = await get_room_activity(
                    room_name=plan.room_name,
                    time_range=plan.time_range,
                )
            else:
                result = await get_activity_history(time_range=plan.time_range)

            return TimeResult(
                response_type="timeline",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        registry = get_model_registry()
        text = await invoke_text(
            prompt=query,
            system_prompt=with_patient_answer_context(
                "You are a kind memory assistant for a dementia patient. "
                "Answer briefly and do not promise unsupported features."
            ),
            model_id=registry.synthesis,
            max_tokens=300,
        )
        return TimeResult(response_type="general", text=text, data={})
    except Exception as exc:
        logger.exception("Time query handling failed")
        return TimeResult(
            response_type="general",
            text=PATIENT_SAFE_ERROR_MESSAGE,
            data={},
        )


if __name__ == "__main__":

    async def main():
        print("Running Time Agent Test...")
        result = await run_time_query("What was I talking about yesterday?")
        print(result.model_dump())
        await close_clients()

    asyncio.run(main())
