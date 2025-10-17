"""Pydantic models shared across the scene resolution workflow."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator


ActivityLiteral = Literal["entered", "picked", "placed", "exited", "carry", "handoff"]


class Appearance(BaseModel):
    top: Optional[str] = Field(default=None)
    bottom: Optional[str] = Field(default=None)
    shoes: Optional[str] = Field(default=None)
    others: Optional[str] = Field(default=None)

    def tokens(self) -> List[str]:
        parts: List[str] = []
        for value in (self.top, self.bottom, self.shoes, self.others):
            if not value:
                continue
            parts.extend(value.lower().split())
        return [token.strip(".,") for token in parts if token.strip()]


class PersonObservation(BaseModel):
    pid_hint: str = Field(default="")
    appearance: Appearance = Field(default_factory=Appearance)
    activities: List[ActivityLiteral] = Field(default_factory=list)


class ObjectObservation(BaseModel):
    name: str
    picked_by: Optional[str] = Field(default=None)
    pick_time_s: float = Field(default=0.0)
    placed_at: Optional[str] = Field(default=None)
    place_time_s: float = Field(default=0.0)
    exited_with: bool = Field(default=False)
    uncertain: bool = Field(default=False)


class AudioUtterance(BaseModel):
    start_s: float
    end_s: float
    text: str


class AudioSummary(BaseModel):
    present: bool = Field(default=False)
    transcript: Optional[str] = Field(default=None)
    utterances: List[AudioUtterance] = Field(default_factory=list)

    @validator("transcript", pre=True, always=True)
    def _normalise_transcript(cls, value, values):  # noqa: D401
        """Ensure transcript is empty when audio is not present."""

        present = values.get("present", False)
        if not present:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None


from typing import Any
class GeminiClip(BaseModel):
    clip_id: str
    room: Literal["A", "B"]
    summary: str = Field(default="")
    people: List[PersonObservation] = Field(default_factory=list)
    objects: List[ObjectObservation] = Field(default_factory=list)
    audio: Optional[AudioSummary] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    event_id: str
    timestamp: datetime
    clip_id: str
    room: Literal["A", "B"]
    actor: Optional[str] = Field(default=None)
    action: str
    description: str
    details: Dict[str, object] = Field(default_factory=dict)


class SceneWorldState(BaseModel):
    objects: Dict[str, Dict[str, object]] = Field(default_factory=dict)
    persons: Dict[str, Dict[str, object]] = Field(default_factory=dict)


class SceneState(BaseModel):
    timeline: List[Event] = Field(default_factory=list)
    world_state: SceneWorldState = Field(default_factory=SceneWorldState)

    def append_event(self, event: Event) -> None:
        timeline = list(self.timeline)
        timeline.append(event)
        timeline.sort(key=lambda item: item.timestamp)
        self.timeline = timeline

    def model_dump_dict(self) -> Dict[str, object]:
        return self.model_dump(mode="python")


__all__ = [
    "ActivityLiteral",
    "Appearance",
    "AudioSummary",
    "AudioUtterance",
    "Event",
    "GeminiClip",
    "ObjectObservation",
    "PersonObservation",
    "SceneState",
    "SceneWorldState",
]
