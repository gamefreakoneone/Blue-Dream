from __future__ import annotations

import datetime
from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, Field

try:
    from .media_paths import normalize_stored_path, to_stored_path
    from .timezone_utils import LOCAL_TZ, now_local
except ImportError:
    from media_paths import normalize_stored_path, to_stored_path
    from timezone_utils import LOCAL_TZ, now_local


ROOMS: dict[int, str] = {
    0: "Bedroom",
    1: "Living Room",
}
ROOM_NAME_TO_ID: dict[str, int] = {name.lower(): room_id for room_id, name in ROOMS.items()}


class MemoryEvent(BaseModel):
    event_id: str
    timestamp: datetime.datetime
    room_number: int
    room_name: str
    video_description: str = ""
    room_objects: list[str] = Field(default_factory=list)
    audio_transcript: str = ""
    screenshot_path: str = ""
    video_path: str = ""
    video_oss_key: str | None = None
    audio_path: str = ""
    semantic_text: str = ""
    danger_candidate: bool = False
    scene_end_state: str = ""
    observed_hazards: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    safety_assessment: dict[str, Any] | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_reason: str = ""
    pinned: bool = False
    lifecycle_status: Literal["active", "consolidated"] = "active"
    consolidated_into: str | None = None


def get_room_name(room_number: int) -> str:
    return ROOMS.get(room_number, f"Room {room_number}")


def normalize_timestamp(value: Any) -> datetime.datetime:
    if value is None:
        dt_value = now_local()
    elif isinstance(value, datetime.datetime):
        dt_value = value
    elif isinstance(value, str):
        try:
            dt_value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt_value = now_local()
    else:
        dt_value = now_local()

    if dt_value.tzinfo is None:
        # MongoDB returns naive UTC datetimes; tag as UTC then convert to local
        dt_value = dt_value.replace(tzinfo=datetime.timezone.utc).astimezone(LOCAL_TZ)
    else:
        dt_value = dt_value.astimezone(LOCAL_TZ)

    return dt_value


def _normalize_room_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_room_objects(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        return []

    cleaned: list[str] = []
    for candidate in candidates:
        item = str(candidate).strip()
        if item:
            cleaned.append(item)
    return cleaned


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_importance(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, parsed))


def _normalize_lifecycle_status(value: Any) -> Literal["active", "consolidated"]:
    return "consolidated" if value == "consolidated" else "active"


def build_semantic_text(event: MemoryEvent) -> str:
    sections = [
        f"Room: {event.room_name}",
        f"Time: {event.timestamp.strftime('%Y-%m-%d %I:%M %p')}",
    ]
    if event.video_description.strip():
        sections.append(f"Video: {event.video_description.strip()}")
    if event.audio_transcript.strip():
        sections.append(f"Audio: {event.audio_transcript.strip()}")
    if event.room_objects:
        sections.append(f"Objects: {', '.join(event.room_objects)}")
    if event.observed_hazards:
        sections.append(f"Safety observations: {', '.join(event.observed_hazards)}")
    if event.scene_end_state.strip():
        sections.append(f"Scene end state: {event.scene_end_state.strip()}")
    return "\n".join(sections)


def memory_event_from_mongo(doc: dict[str, Any]) -> MemoryEvent:
    room_number = _normalize_room_number(doc.get("room_number", 0))
    room_name = _normalize_text(doc.get("room_name")) or get_room_name(room_number)
    event_id = _normalize_text(doc.get("event_id"))
    if not event_id:
        mongo_id = doc.get("_id")
        event_id = str(mongo_id) if mongo_id is not None else ""

    event = MemoryEvent(
        event_id=event_id,
        timestamp=normalize_timestamp(doc.get("timestamp")),
        room_number=room_number,
        room_name=room_name,
        video_description=_normalize_text(doc.get("video_description")),
        room_objects=_normalize_room_objects(doc.get("room_objects")),
        audio_transcript=_normalize_text(doc.get("audio_transcript")),
        screenshot_path=normalize_stored_path(doc.get("screenshot_path")) or "",
        video_path=normalize_stored_path(doc.get("video_path")) or "",
        video_oss_key=normalize_stored_path(doc.get("video_oss_key")),
        audio_path=normalize_stored_path(doc.get("audio_path")) or "",
        semantic_text="",
        danger_candidate=bool(doc.get("danger_candidate", False)),
        scene_end_state=_normalize_text(doc.get("scene_end_state")),
        observed_hazards=_normalize_room_objects(doc.get("observed_hazards")),
        uncertainties=_normalize_room_objects(doc.get("uncertainties")),
        safety_assessment=doc.get("safety_assessment")
        if isinstance(doc.get("safety_assessment"), dict)
        else None,
        importance=_normalize_importance(doc.get("importance", 0.5)),
        importance_reason=_normalize_text(doc.get("importance_reason")),
        pinned=bool(doc.get("pinned", False)),
        lifecycle_status=_normalize_lifecycle_status(doc.get("lifecycle_status")),
        consolidated_into=_normalize_text(doc.get("consolidated_into")) or None,
    )
    event.semantic_text = _normalize_text(doc.get("semantic_text")) or build_semantic_text(event)
    return event


def new_memory_event(
    *,
    timestamp: datetime.datetime,
    room_number: int,
    video_description: str,
    room_objects: list[str],
    audio_transcript: str,
    screenshot_path: str,
    video_path: str,
    audio_path: str,
    video_oss_key: str | None = None,
    danger_candidate: bool = False,
    scene_end_state: str = "",
    observed_hazards: list[str] | None = None,
    uncertainties: list[str] | None = None,
    safety_assessment: dict[str, Any] | None = None,
) -> MemoryEvent:
    object_id = ObjectId()
    event = MemoryEvent(
        event_id=str(object_id),
        timestamp=normalize_timestamp(timestamp),
        room_number=_normalize_room_number(room_number),
        room_name=get_room_name(_normalize_room_number(room_number)),
        video_description=_normalize_text(video_description),
        room_objects=_normalize_room_objects(room_objects),
        audio_transcript=_normalize_text(audio_transcript),
        screenshot_path=to_stored_path(screenshot_path) or "",
        video_path=to_stored_path(video_path) or "",
        video_oss_key=to_stored_path(video_oss_key),
        audio_path=to_stored_path(audio_path) or "",
        semantic_text="",
        danger_candidate=bool(danger_candidate),
        scene_end_state=_normalize_text(scene_end_state),
        observed_hazards=_normalize_room_objects(observed_hazards or []),
        uncertainties=_normalize_room_objects(uncertainties or []),
        safety_assessment=safety_assessment,
    )
    event.semantic_text = build_semantic_text(event)
    return event


def memory_event_to_mongo(event: MemoryEvent) -> dict[str, Any]:
    document = {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "room_number": event.room_number,
        "room_name": event.room_name,
        "video_description": event.video_description,
        "room_objects": event.room_objects,
        "audio_transcript": event.audio_transcript,
        "screenshot_path": to_stored_path(event.screenshot_path) or "",
        "video_path": to_stored_path(event.video_path) or "",
        "audio_path": to_stored_path(event.audio_path) or "",
        "semantic_text": event.semantic_text,
        "danger_candidate": event.danger_candidate,
        "scene_end_state": event.scene_end_state,
        "observed_hazards": event.observed_hazards,
        "uncertainties": event.uncertainties,
        "safety_assessment": event.safety_assessment,
        "importance": event.importance,
        "importance_reason": event.importance_reason,
        "pinned": event.pinned,
        "lifecycle_status": event.lifecycle_status,
        "consolidated_into": event.consolidated_into,
    }
    if ObjectId.is_valid(event.event_id):
        document["_id"] = ObjectId(event.event_id)
    if event.video_oss_key:
        document["video_oss_key"] = to_stored_path(event.video_oss_key)
    return document
