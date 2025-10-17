"""Lightweight question-answering helpers for scene state and transcripts."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json")).expanduser().resolve()
TRANSCRIPTS_DIR = Path(
    os.environ.get("TRANSCRIPTS_DIR", STATE_PATH.parent / "transcripts")
).expanduser().resolve()
MAX_TRANSCRIPT_FILES = int(os.environ.get("TRANSCRIPTS_MAX_FILES", "5"))


@dataclass
class TimelineEvent:
    """A single entry in a scene timeline."""

    description: str
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "TimelineEvent":
        description = str(
            data.get("description")
            or data.get("summary")
            or data.get("text")
            or ""
        ).strip()
        timestamp = data.get("timestamp") or data.get("time")
        metadata = {
            key: value
            for key, value in data.items()
            if key not in {"description", "summary", "text", "timestamp", "time"}
        }
        return cls(description=description, timestamp=timestamp, metadata=metadata)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "description": self.description,
            "timestamp": self.timestamp,
        }
        if self.metadata:
            base["metadata"] = self.metadata
        return base


@dataclass
class SceneState:
    """Container describing the current world state and timeline."""

    world_state: str = ""
    timeline: List[TimelineEvent] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "SceneState":
        if not path.exists():
            logger.warning("Scene state file does not exist: %s", path)
            return cls()

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to load scene state from %s", path)
            return cls()

        world_state = str(
            data.get("world_state")
            or data.get("summary")
            or data.get("description")
            or ""
        ).strip()
        timeline_data = data.get("timeline") or data.get("events") or []
        timeline: List[TimelineEvent] = []
        for entry in timeline_data:
            if isinstance(entry, dict):
                timeline.append(TimelineEvent.from_mapping(entry))
            else:
                timeline.append(TimelineEvent(description=str(entry)))

        extras = {
            key: value
            for key, value in data.items()
            if key not in {"world_state", "summary", "description", "timeline", "events"}
        }
        return cls(world_state=world_state, timeline=timeline, extras=extras)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_state": self.world_state,
            "timeline": [event.to_dict() for event in self.timeline],
            "extras": self.extras,
        }


@dataclass
class Transcript:
    """A transcript artifact pulled into the QA context."""

    path: Path
    text: str

    def citation(self) -> str:
        return f"transcript:{self.path.name}"


@dataclass
class SourceChunk:
    text: str
    citation: str


def load_scene_state(state_path: Optional[Path] = None) -> SceneState:
    """Load the scene state from disk."""

    path = Path(state_path) if state_path is not None else STATE_PATH
    return SceneState.from_file(path)


def _load_transcripts(directory: Path, limit: int) -> List[Transcript]:
    if not directory.exists() or not directory.is_dir():
        return []

    paths = sorted(
        (p for p in directory.iterdir() if p.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    transcripts: List[Transcript] = []
    for path in paths[:limit]:
        try:
            if path.suffix.lower() == ".json":
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                text = _flatten_json_transcript(payload)
            else:
                text = path.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to read transcript file %s", path)
            continue

        text = text.strip()
        if text:
            transcripts.append(Transcript(path=path, text=text))
    return transcripts


def _flatten_json_transcript(payload: Any) -> str:
    if isinstance(payload, dict):
        if "messages" in payload and isinstance(payload["messages"], Iterable) and not isinstance(
            payload["messages"], (str, bytes)
        ):
            parts: List[str] = []
            for message in payload["messages"]:
                if isinstance(message, dict):
                    role = message.get("role", "")
                    content = message.get("content", "")
                    parts.append(f"{role}: {content}".strip())
                else:
                    parts.append(str(message))
            return "\n".join(part for part in parts if part)
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, list):
        return "\n".join(_flatten_json_transcript(item) for item in payload)
    return str(payload)


def _build_sources(state: SceneState, transcripts: Sequence[Transcript]) -> List[SourceChunk]:
    sources: List[SourceChunk] = []
    if state.world_state:
        sources.append(
            SourceChunk(text=state.world_state, citation="state:world_state")
        )

    for index, event in enumerate(state.timeline):
        if not event.description:
            continue
        label = f"state:timeline[{index}]"
        if event.timestamp:
            label += f"@{event.timestamp}"
        sources.append(SourceChunk(text=event.description, citation=label))

    for transcript in transcripts:
        sources.append(SourceChunk(text=transcript.text, citation=transcript.citation()))

    return sources


def _extract_keywords(question: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9']+", question.lower())
    keywords = [token for token in tokens if len(token) > 2]
    # Deduplicate while preserving order
    seen = set()
    ordered: List[str] = []
    for keyword in keywords:
        if keyword not in seen:
            seen.add(keyword)
            ordered.append(keyword)
    return ordered


def _score_text(text: str, keywords: Sequence[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(keyword) for keyword in keywords)


def answer(question: str) -> Dict[str, Any]:
    """Return a naive keyword-based answer and citations for a question."""

    question = question.strip()
    if not question:
        return {"answer": "", "citations": []}

    state = load_scene_state()
    transcripts = _load_transcripts(TRANSCRIPTS_DIR, MAX_TRANSCRIPT_FILES)
    sources = _build_sources(state, transcripts)

    keywords = _extract_keywords(question)
    best_chunk: Optional[SourceChunk] = None
    best_score = -1

    for chunk in sources:
        if not chunk.text:
            continue
        score = _score_text(chunk.text, keywords) if keywords else len(chunk.text)
        if score > best_score:
            best_score = score
            best_chunk = chunk

    if best_chunk and best_score > 0:
        answer_text = best_chunk.text
        citations = [best_chunk.citation]
    elif best_chunk:
        # No keyword overlap; fall back to the most informative chunk we saw.
        answer_text = best_chunk.text
        citations = [best_chunk.citation]
    else:
        answer_text = "I'm not sure yet."
        citations = []

    return {"answer": answer_text, "citations": citations}


__all__ = [
    "STATE_PATH",
    "TRANSCRIPTS_DIR",
    "SceneState",
    "TimelineEvent",
    "answer",
    "load_scene_state",
]
