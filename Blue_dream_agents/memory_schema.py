from __future__ import annotations

import datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, Field

try:
    from .timezone_utils import LOCAL_TZ, now_local
except ImportError:
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
    audio_path: str = ""
    semantic_text: str


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
        dt_value = dt_value.replace(tzinfo=datetime.timezone.utc)

    return dt_value.astimezone(LOCAL_TZ)


def _normalize_room_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_room_objects(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = value.split(",")
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


def build_semantic_text(event: MemoryEvent) -> str:
    video_description = event.video_description or "None"
    audio_transcript = event.audio_transcript or "None"
    room_objects = ", ".join(event.room_objects) if event.room_objects else "none"

    return "\n".join(
        [
            f"Room: {event.room_name}",
            f"Time: {event.timestamp.strftime('%Y-%m-%d %I:%M %p')}",
            f"Video: {video_description}",
            f"Audio: {audio_transcript}",
            f"Objects: {room_objects}",
        ]
    )


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
        screenshot_path=_normalize_text(doc.get("screenshot_path")),
        video_path=_normalize_text(doc.get("video_path")),
        audio_path=_normalize_text(doc.get("audio_path")),
        semantic_text="",
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
        screenshot_path=_normalize_text(screenshot_path),
        video_path=_normalize_text(video_path),
        audio_path=_normalize_text(audio_path),
        semantic_text="",
    )
    event.semantic_text = build_semantic_text(event)
    return event


def memory_event_to_mongo(event: MemoryEvent) -> dict[str, Any]:
    return {
        "_id": ObjectId(event.event_id),
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "room_number": event.room_number,
        "room_name": event.room_name,
        "video_description": event.video_description,
        "room_objects": event.room_objects,
        "audio_transcript": event.audio_transcript,
        "screenshot_path": event.screenshot_path,
        "video_path": event.video_path,
        "audio_path": event.audio_path,
        "semantic_text": event.semantic_text,
    }
