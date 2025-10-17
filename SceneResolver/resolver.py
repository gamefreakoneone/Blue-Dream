"""Scene resolution pipeline powered by a LangGraph-style workflow."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import state_store
from .schemas import Appearance, Event, GeminiClip, PersonObservation, SceneState

from langgraph.graph import START, END, StateGraph


_IDENTITIES_PATH = Path(os.environ.get("IDENTITIES_FILE", "Environment/identities.json")).expanduser()
_IDENTITY_CACHE: Optional[Dict[str, Dict[str, Iterable[str]]]] = None
_UNKNOWN_COUNTER = count(1)


def load_identities(path: Optional[Path] = None) -> Dict[str, Dict[str, Iterable[str]]]:
    """Load the appearance → identity mapping."""

    global _IDENTITY_CACHE
    if path is None:
        path = _IDENTITIES_PATH

    if _IDENTITY_CACHE is not None and path == _IDENTITIES_PATH:
        return _IDENTITY_CACHE

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        data = {}

    normalised: Dict[str, Dict[str, Iterable[str]]] = {}
    for name, spec in data.items():
        if not isinstance(spec, dict):
            continue
        normalised[name] = {
            "top": tuple(str(value) for value in spec.get("top", [])),
            "bottom": tuple(str(value) for value in spec.get("bottom", [])),
            "shoes": tuple(str(value) for value in spec.get("shoes", [])),
            "notes": tuple(str(value) for value in spec.get("notes", [])),
        }

    if path == _IDENTITIES_PATH:
        _IDENTITY_CACHE = normalised
    return normalised


def _tokenise_descriptor(descriptor: str) -> List[str]:
    return [token.strip(".,").lower() for token in descriptor.split() if token.strip()]


def _identity_tokens() -> Dict[str, List[str]]:
    tokens: Dict[str, List[str]] = {}
    for name, spec in load_identities().items():
        collected: List[str] = []
        for values in spec.values():
            for value in values:
                collected.extend(_tokenise_descriptor(value))
        tokens[name] = collected
    return tokens


def _next_unknown() -> str:
    return f"Unknown_{next(_UNKNOWN_COUNTER)}"


def resolve_identity(appearance: Appearance, hint: Optional[str] = None) -> str:
    """Resolve an appearance profile to a known identity if possible."""

    if hint:
        for known in load_identities().keys():
            if hint.strip().lower() == known.lower():
                return known

    tokens = set(appearance.tokens())
    if hint:
        tokens.update(_tokenise_descriptor(hint))

    if not tokens:
        return _next_unknown()

    scored: List[Tuple[int, str]] = []
    for name, profile_tokens in _identity_tokens().items():
        score = len(tokens.intersection(profile_tokens))
        if score > 0:
            scored.append((score, name))

    if not scored:
        return _next_unknown()

    scored.sort(reverse=True)
    best_score = scored[0][0]
    best_names = [name for score, name in scored if score == best_score]
    if len(best_names) == 1:
        return best_names[0]
    return _next_unknown()


def _associate_people(resolved: List[Tuple[str, PersonObservation]], alias: Optional[str]) -> Optional[str]:
    if not alias:
        return None
    alias_lower = alias.lower()
    for identity, person in resolved:
        if person.pid_hint and person.pid_hint.lower() == alias_lower:
            return identity
        if identity.lower() == alias_lower:
            return identity
    return alias


def _parse_clip(state: Dict[str, object]) -> Dict[str, object]:
    clip = GeminiClip.model_validate(state["raw_clip"])
    return {"clip": clip}


def _load_state(_: Dict[str, object]) -> Dict[str, object]:
    scene_state = state_store.load_state()
    return {"scene_state": scene_state}


def _resolve_people(state: Dict[str, object]) -> Dict[str, object]:
    clip: GeminiClip = state["clip"]
    resolved: List[Tuple[str, PersonObservation]] = []
    for person in clip.people:
        identity = resolve_identity(person.appearance, hint=person.pid_hint)
        resolved.append((identity, person))
    return {"resolved_people": resolved}


def _build_events(state: Dict[str, object]) -> Dict[str, object]:
    clip: GeminiClip = state["clip"]
    resolved: List[Tuple[str, PersonObservation]] = state.get("resolved_people", [])
    events: List[Event] = []
    base_time = datetime.utcnow()
    sequence = 0

    for identity, person in resolved:
        for activity in person.activities:
            event_id = f"{clip.clip_id}:{identity}:{activity}:{sequence}"
            description = f"{identity} {activity} in room {clip.room}"
            events.append(
                Event(
                    event_id=event_id,
                    timestamp=base_time,
                    clip_id=clip.clip_id,
                    room=clip.room,
                    actor=identity,
                    action=activity,
                    description=description,
                    details={"pid_hint": person.pid_hint},
                )
            )
            sequence += 1
            base_time = base_time + timedelta(microseconds=1_000)

    for obj in clip.objects:
        holder = _associate_people(resolved, obj.picked_by)
        if obj.picked_by:
            event_id = f"{clip.clip_id}:{obj.name}:picked:{sequence}"
            description = f"{holder or obj.picked_by} picked {obj.name}"
            events.append(
                Event(
                    event_id=event_id,
                    timestamp=base_time,
                    clip_id=clip.clip_id,
                    room=clip.room,
                    actor=holder,
                    action="picked",
                    description=description,
                    details={"object": obj.name, "picked_by": obj.picked_by},
                )
            )
            sequence += 1
            base_time = base_time + timedelta(microseconds=1_000)
        if obj.placed_at:
            event_id = f"{clip.clip_id}:{obj.name}:placed:{sequence}"
            description = f"{holder or obj.picked_by or 'Someone'} placed {obj.name} at {obj.placed_at}"
            events.append(
                Event(
                    event_id=event_id,
                    timestamp=base_time,
                    clip_id=clip.clip_id,
                    room=clip.room,
                    actor=holder,
                    action="placed",
                    description=description,
                    details={"object": obj.name, "placed_at": obj.placed_at},
                )
            )
            sequence += 1
            base_time = base_time + timedelta(microseconds=1_000)
        if obj.exited_with:
            event_id = f"{clip.clip_id}:{obj.name}:exited:{sequence}"
            description = f"{holder or obj.picked_by or 'Someone'} exited with {obj.name}"
            events.append(
                Event(
                    event_id=event_id,
                    timestamp=base_time,
                    clip_id=clip.clip_id,
                    room=clip.room,
                    actor=holder,
                    action="exited",
                    description=description,
                    details={"object": obj.name},
                )
            )
            sequence += 1
            base_time = base_time + timedelta(microseconds=1_000)

    return {"events": events}


def _update_world(state: Dict[str, object]) -> Dict[str, object]:
    clip: GeminiClip = state["clip"]
    scene_state: SceneState = state["scene_state"]
    resolved: List[Tuple[str, PersonObservation]] = state.get("resolved_people", [])
    events: List[Event] = state.get("events", [])
    timestamp = datetime.utcnow().isoformat()

    for identity, person in resolved:
        person_entry = scene_state.world_state.persons.setdefault(identity, {})
        person_entry.update(
            {
                "room": clip.room,
                "last_seen": timestamp,
                "clip_id": clip.clip_id,
                "appearance": person.appearance.model_dump(mode="python"),
                "pid_hint": person.pid_hint,
                "metadata": clip.metadata,
            }
        )
        if events:
            for event in reversed(events):
                if event.actor == identity:
                    person_entry["last_activity"] = event.action
                    break

    for obj in clip.objects:
        holder = _associate_people(resolved, obj.picked_by)
        object_entry = scene_state.world_state.objects.setdefault(obj.name, {})
        object_entry.update(
            {
                "room": clip.room,
                "last_seen": timestamp,
                "clip_id": clip.clip_id,
                "picked_by": holder or obj.picked_by,
                "placed_at": obj.placed_at,
                "uncertain": obj.uncertain,
                "metadata": clip.metadata,
            }
        )
        if obj.exited_with:
            object_entry["location"] = "exited"
        elif obj.placed_at:
            object_entry["location"] = obj.placed_at
        elif holder:
            object_entry["location"] = f"held_by:{holder}"

    for event in events:
        scene_state.append_event(event)

    state_store.save_state(scene_state)
    return {"scene_state": scene_state}


def _build_graph():
    graph = StateGraph(dict)
    graph.add_node("load_state", _load_state)
    graph.add_node("parse_clip", _parse_clip)
    graph.add_node("resolve_people", _resolve_people)
    graph.add_node("build_events", _build_events)
    graph.add_node("update_world", _update_world)
    graph.add_edge(START, "load_state")
    graph.add_edge("load_state", "parse_clip")
    graph.add_edge("parse_clip", "resolve_people")
    graph.add_edge("resolve_people", "build_events")
    graph.add_edge("build_events", "update_world")
    graph.add_edge("update_world", END)
    return graph.compile()


_INGEST_GRAPH = _build_graph()


def ingest(gemini_json: Dict[str, object]) -> SceneState:
    """Public entry point to ingest Gemini JSON into the scene state."""

    state: Dict[str, object] = {"raw_clip": gemini_json}
    result = _INGEST_GRAPH(state)
    scene_state: SceneState = result["scene_state"]
    return scene_state


__all__ = ["ingest", "load_identities", "resolve_identity"]
