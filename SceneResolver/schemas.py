"""Data models for describing Gemini payloads and the resolved scene state."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class GeminiEntity(BaseModel):
    """Entity as described by the Gemini JSON payload."""

    entity_id: Optional[str] = Field(default=None, alias="id")
    name: Optional[str] = None
    type: Optional[str] = None
    appearance: Dict[str, Any] = Field(default_factory=dict)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @root_validator(pre=True)
    def _normalise_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(values)
        data.setdefault("appearance", data.get("looks", {}))
        data.setdefault("attributes", data.get("state", {}))
        metadata = data.get("metadata") or {}
        for key in list(data.keys()):
            if key in {"id", "name", "type", "appearance", "attributes", "metadata"}:
                continue
            metadata.setdefault(key, data.pop(key))
        data["metadata"] = metadata
        return data

    class Config:
        allow_population_by_field_name = True


class GeminiEvent(BaseModel):
    """Event entry supplied by the Gemini payload."""

    event_id: Optional[str] = Field(default=None, alias="id")
    timestamp: datetime
    action: Optional[str] = None
    summary: Optional[str] = None
    actors: List[GeminiEntity] = Field(default_factory=list)
    targets: List[GeminiEntity] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @root_validator(pre=True)
    def _normalise_event(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(values)
        data["event_id"] = data.get("event_id") or data.get("id")
        data["timestamp"] = data.get("timestamp") or data.get("time") or data.get("event_time")
        data.setdefault("action", data.get("verb"))
        data.setdefault("summary", data.get("description"))

        if not data.get("actors"):
            participants = data.get("participants") or data.get("subjects")
            if isinstance(participants, list):
                data["actors"] = participants
        if not data.get("targets"):
            entities = data.get("entities") or []
            if isinstance(entities, list):
                target_like = [entry for entry in entities if isinstance(entry, dict) and entry.get("role") in {"object", "target"}]
                actor_like = [entry for entry in entities if isinstance(entry, dict) and entry.get("role") in {"actor", "subject", "person"}]
                if actor_like and not data.get("actors"):
                    data["actors"] = actor_like
                if target_like and not data.get("targets"):
                    data["targets"] = target_like

        metadata = data.get("metadata") or {}
        known = {
            "event_id",
            "id",
            "timestamp",
            "time",
            "event_time",
            "action",
            "verb",
            "summary",
            "description",
            "actors",
            "targets",
            "participants",
            "subjects",
            "entities",
            "metadata",
        }
        for key in list(data.keys()):
            if key in known:
                continue
            metadata.setdefault(key, data.pop(key))
        data["metadata"] = metadata
        return data

    @validator("timestamp", pre=True)
    def _coerce_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        raise ValueError(f"Unsupported timestamp format: {value!r}")

    class Config:
        allow_population_by_field_name = True


class GeminiPayload(BaseModel):
    """Top-level payload returned by the Gemini parser."""

    events: List[GeminiEvent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @root_validator(pre=True)
    def _normalise_payload(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(values)
        data.setdefault("events", data.get("timeline") or data.get("entries") or [])
        metadata = data.get("metadata") or {}
        for key in list(data.keys()):
            if key in {"events", "timeline", "entries", "metadata"}:
                continue
            metadata.setdefault(key, data.pop(key))
        data["metadata"] = metadata
        return data

    class Config:
        allow_population_by_field_name = True


class EventActor(BaseModel):
    """Participant in a resolved event."""

    entity_id: str
    name: Optional[str] = None
    type: str = "unknown"
    appearance: Dict[str, Any] = Field(default_factory=dict)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """Normalised event stored in the scene timeline."""

    id: str
    timestamp: datetime
    action: str
    summary: Optional[str] = None
    actor: Optional[EventActor] = None
    target: Optional[EventActor] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EntityState(BaseModel):
    """Current understanding of an entity within the scene."""

    entity_id: str
    name: Optional[str] = None
    type: str = "unknown"
    appearance: Dict[str, Any] = Field(default_factory=dict)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    last_event_id: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SceneState(BaseModel):
    """Persisted state of the scene."""

    timeline: List[Event] = Field(default_factory=list)
    world_state: Dict[str, EntityState] = Field(default_factory=dict)
