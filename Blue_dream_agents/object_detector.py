from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

try:
    from .gemini_spatial import highlight_object_with_gemini
    from .llm.model_registry import get_model_registry
    from .llm.strands_runtime import invoke_multimodal_structured, invoke_structured
    from .memory_schema import MemoryEvent, ROOMS, memory_event_from_mongo
    from .timezone_utils import now_local
except ImportError:
    from gemini_spatial import highlight_object_with_gemini
    from llm.model_registry import get_model_registry
    from llm.strands_runtime import invoke_multimodal_structured, invoke_structured
    from memory_schema import MemoryEvent, ROOMS, memory_event_from_mongo
    from timezone_utils import now_local


logger = logging.getLogger(__name__)
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
HISTORY_LOOKBACK_HOURS = 48
HISTORY_EVENT_LIMIT = 80


class SearchResult(BaseModel):
    found: bool = Field(description="Whether the object was found")
    room_number: Optional[int] = Field(default=None)
    room_name: Optional[str] = Field(default=None)
    matched_object: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    highlighted_image_path: Optional[str] = Field(default=None)
    evidence_type: Literal[
        "current_visual_highlight",
        "current_visual_text_only",
        "historical_last_known",
        "not_found",
    ] = Field(default="not_found")
    confidence: Literal["high", "medium", "low"] = Field(default="low")
    anchor_event_id: Optional[str] = Field(default=None)
    anchor_timestamp: Optional[str] = Field(default=None)
    highlight_status: Literal[
        "generated",
        "failed_after_visual_match",
        "not_attempted",
    ] = Field(default="not_attempted")


class ObjectQueryIntent(BaseModel):
    object_name: str
    room_id: Optional[int] = None


class ObjectVisionCheck(BaseModel):
    found: bool = False
    description: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    matched_object: Optional[str] = None


class ObjectLastKnownResult(BaseModel):
    found: bool = False
    room_name: Optional[str] = None
    anchor_event_id: Optional[str] = None
    anchor_timestamp: Optional[str] = None
    status: Literal["placed", "carried_out_of_frame", "removed", "uncertain"] = (
        "uncertain"
    )
    summary: str = ""
    confidence: Literal["high", "medium", "low"] = "low"


MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
_mongo_client: Optional[AsyncIOMotorClient] = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGO_URI)
    return _mongo_client


async def close_clients():
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None


async def _get_latest_room_states() -> List[MemoryEvent]:
    collection = get_mongo_client().dementia_assistance.events
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$room_number", "latest_doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$latest_doc"}},
    ]

    room_states: List[MemoryEvent] = []
    async for doc in collection.aggregate(pipeline):
        room_states.append(memory_event_from_mongo(doc))
    return room_states


async def _get_recent_events(
    *,
    hours: int = HISTORY_LOOKBACK_HOURS,
    room_number: Optional[int] = None,
    limit: int = HISTORY_EVENT_LIMIT,
) -> List[MemoryEvent]:
    collection = get_mongo_client().dementia_assistance.events
    end_dt = now_local()
    start_dt = end_dt - datetime.timedelta(hours=hours)
    query: Dict[str, Any] = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}
    if room_number is not None:
        query["room_number"] = room_number

    cursor = collection.find(query).sort("timestamp", -1).limit(limit)
    events: List[MemoryEvent] = []
    async for doc in cursor:
        events.append(memory_event_from_mongo(doc))
    return events


async def _parse_query_intent(user_query: str) -> ObjectQueryIntent:
    registry = get_model_registry()
    prompt = (
        f"Query: {user_query}\n"
        f"Rooms: {json.dumps(ROOMS)}\n"
        "Extract the target object and optional room id if the user mentioned one."
    )
    return await invoke_structured(
        prompt=prompt,
        output_model=ObjectQueryIntent,
        system_prompt=(
            "You parse lost-object queries for a home monitoring assistant. "
            "If the room is unclear, leave room_id null."
        ),
        model_id=registry.router,
        structured_output_prompt="Return the object name and optional room id.",
        max_tokens=300,
    )


async def _check_image_worker(
    object_name: str, room: MemoryEvent
) -> Optional[Dict[str, Any]]:
    if not room.screenshot_path or not os.path.exists(room.screenshot_path):
        return None

    registry = get_model_registry()
    inventory_hint = ", ".join(room.room_objects) if room.room_objects else "none"
    try:
        result = await invoke_multimodal_structured(
            text_prompt=(
                f"Target object: {object_name}\n"
                f"Room: {room.room_name}\n"
                f"Current room inventory hints: {inventory_hint}\n"
                "Decide whether the image visibly contains the target object or a "
                "clear synonym. Treat the inventory only as synonym guidance, not "
                "as proof. If found, describe where it is in one short grounded "
                "sentence and provide the matched object string when a synonym or "
                "specific variant is visible."
            ),
            image_path=room.screenshot_path,
            output_model=ObjectVisionCheck,
            system_prompt=(
                "You inspect room images for a lost-object assistant. Only mark found "
                "true when the object is visibly present in the current image."
            ),
            model_id=registry.vision,
            fallback_model_id=registry.vision_fallback,
            structured_output_prompt=(
                "Return found, description, confidence, and optional matched_object. "
                "If the object is not visible, return found=false."
            ),
            max_tokens=300,
        )
    except Exception as exc:
        logger.warning(
            "Image inspection failed for room %s: %s", room.room_number, exc
        )
        return None

    if result.found:
        return {
            "room": room,
            "description": result.description or "Object visible in room.",
            "confidence": _normalize_confidence(result.confidence),
            "matched_object": (result.matched_object or object_name).strip() or object_name,
        }
    return None


async def _parallel_vision_search(
    object_name: str, room_states: List[MemoryEvent]
) -> List[Dict[str, Any]]:
    results = await asyncio.gather(
        *[_check_image_worker(object_name, room) for room in room_states]
    )
    matches = [result for result in results if result]
    matches.sort(
        key=lambda result: (
            CONFIDENCE_RANK[result["confidence"]],
            result["room"].timestamp,
        ),
        reverse=True,
    )
    return matches


def _normalize_confidence(value: str | None) -> Literal["high", "medium", "low"]:
    normalized = str(value or "").strip().lower()
    if normalized in CONFIDENCE_RANK:
        return normalized  # type: ignore[return-value]
    return "low"


def _finalize_sentence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    return f"{cleaned}."


def _current_visual_description(
    object_name: str,
    room_name: str,
    grounded_description: str,
    *,
    highlight_generated: bool,
) -> str:
    description = _finalize_sentence(grounded_description)
    if not description:
        description = f"I can see your {object_name} in the {room_name}."
    elif room_name.lower() not in description.lower():
        description = f"{description[:-1]} in the {room_name}."

    if highlight_generated:
        return description
    return (
        f"{description} I could see it in the current room image, "
        "but I couldn't generate a highlighted image."
    )


def _serialize_history_events(events: List[MemoryEvent]) -> List[Dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "room_name": event.room_name,
            "video_description": event.video_description[:1200],
            "room_objects": event.room_objects,
            "audio_transcript": event.audio_transcript[:800],
            "screenshot_available": bool(event.screenshot_path),
        }
        for event in events
    ]


async def _analyze_last_known_location(
    search_term: str,
    history_events: List[MemoryEvent],
) -> Optional[ObjectLastKnownResult]:
    if not history_events:
        return None

    registry = get_model_registry()
    result = await invoke_structured(
        prompt=(
            f"User is looking for: {search_term}\n"
            "The object was not visible in any current room snapshot.\n"
            "Here are recent monitoring events, newest first:\n"
            f"{json.dumps(_serialize_history_events(history_events), indent=2)}"
        ),
        output_model=ObjectLastKnownResult,
        system_prompt=(
            "You infer the last known location of a missing household item from "
            "home-monitoring events. Prefer direct mentions in video_description. "
            "Use room_objects only as supporting evidence, never as sole proof. "
            "Use audio_transcript only when it directly supports the object's "
            "location or handling. Never invent a current location. If the person "
            "was carrying the object and then moved out of frame, mark "
            "status='carried_out_of_frame' and say it was last seen being carried "
            "in that room. Mark found=false when there is no reliable grounded clue."
        ),
        model_id=registry.synthesis,
        structured_output_prompt=(
            "Return found, room_name, anchor_event_id, anchor_timestamp, status, "
            "summary, and confidence. Use only event IDs and timestamps from the "
            "supplied events."
        ),
        max_tokens=500,
    )

    if not result.found or not result.summary.strip():
        return None

    event_map = {event.event_id: event for event in history_events}
    anchor_event = event_map.get((result.anchor_event_id or "").strip())
    if anchor_event is not None:
        result.anchor_event_id = anchor_event.event_id
        result.anchor_timestamp = anchor_event.timestamp.isoformat()
        result.room_name = result.room_name or anchor_event.room_name
    else:
        result.anchor_event_id = None
        result.anchor_timestamp = None

    result.confidence = _normalize_confidence(result.confidence)
    result.summary = _finalize_sentence(result.summary)
    return result


async def _highlight_object(
    object_name: str,
    image_path: str,
    *,
    matched_object: Optional[str] = None,
    grounding_text: Optional[str] = None,
    output_dir: str = "Storage/highlighted",
) -> Optional[str]:
    output_dir = os.path.abspath(output_dir)

    try:
        return await highlight_object_with_gemini(
            image_path=image_path,
            object_name=object_name,
            matched_object=matched_object,
            grounding_text=grounding_text,
            output_dir=output_dir,
        )
    except Exception as exc:
        logger.warning("Highlight failed for %s: %s", object_name, exc)
        return None


async def search_for_object(user_query: str) -> SearchResult:
    try:
        room_states = await _get_latest_room_states()
        if not room_states:
            return SearchResult(
                found=False,
                description="No monitoring data available.",
                evidence_type="not_found",
                highlight_status="not_attempted",
            )

        parsed = await _parse_query_intent(user_query)
        target_object = parsed.object_name or user_query
        target_room_id = parsed.room_id

        rooms_to_search = room_states
        if target_room_id is not None:
            rooms_to_search = [
                room for room in room_states if room.room_number == int(target_room_id)
            ]
            if not rooms_to_search:
                return SearchResult(
                    found=False,
                    description=f"Room {target_room_id} has no data.",
                    evidence_type="not_found",
                    highlight_status="not_attempted",
                )

        current_visual_matches = await _parallel_vision_search(
            target_object, rooms_to_search
        )
        if current_visual_matches:
            best_match = current_visual_matches[0]
            room = best_match["room"]
            highlight_path = await _highlight_object(
                target_object,
                room.screenshot_path,
                matched_object=best_match["matched_object"],
                grounding_text=best_match["description"] or room.video_description,
            )
            return SearchResult(
                found=True,
                room_number=room.room_number,
                room_name=room.room_name,
                matched_object=best_match["matched_object"],
                description=_current_visual_description(
                    target_object,
                    room.room_name,
                    best_match["description"],
                    highlight_generated=bool(highlight_path),
                ),
                highlighted_image_path=highlight_path,
                evidence_type=(
                    "current_visual_highlight"
                    if highlight_path
                    else "current_visual_text_only"
                ),
                confidence=best_match["confidence"],
                anchor_event_id=room.event_id,
                anchor_timestamp=room.timestamp.isoformat(),
                highlight_status=(
                    "generated"
                    if highlight_path
                    else "failed_after_visual_match"
                ),
            )

        history_events = await _get_recent_events(
            hours=HISTORY_LOOKBACK_HOURS,
            room_number=target_room_id,
            limit=HISTORY_EVENT_LIMIT,
        )
        historical_match = await _analyze_last_known_location(
            target_object,
            history_events,
        )
        if historical_match:
            return SearchResult(
                found=True,
                room_number=next(
                    (
                        event.room_number
                        for event in history_events
                        if event.event_id == historical_match.anchor_event_id
                    ),
                    None,
                ),
                room_name=historical_match.room_name,
                matched_object=target_object,
                description=historical_match.summary,
                highlighted_image_path=None,
                evidence_type="historical_last_known",
                confidence=historical_match.confidence,
                anchor_event_id=historical_match.anchor_event_id,
                anchor_timestamp=historical_match.anchor_timestamp,
                highlight_status="not_attempted",
            )

        return SearchResult(
            found=False,
            description=(
                f"I couldn't see your {target_object} in the current room images, "
                "and I don't have a reliable last-known location for it."
            ),
            evidence_type="not_found",
            highlight_status="not_attempted",
        )
    except Exception as exc:
        logger.exception("Object search failed.")
        return SearchResult(
            found=False,
            description=f"System error during search: {exc}",
            evidence_type="not_found",
            highlight_status="not_attempted",
        )


async def run_object_query(query: str) -> SearchResult:
    return await search_for_object(query)


if __name__ == "__main__":

    async def main():
        print("Running Object Detector Test...")
        result = await run_object_query("Where is my white story book?")
        print(result.model_dump())
        await close_clients()

    asyncio.run(main())
