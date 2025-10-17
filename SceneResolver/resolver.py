"""Scene ingestion and resolution utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from uuid import uuid4

from pydantic import ValidationError

from . import state_store
from .schemas import (
    EntityState,
    Event,
    EventActor,
    GeminiEntity,
    GeminiPayload,
    SceneState,
)

IDENTITIES_PATH = Path("Environment/identities.json")


def _normalise_section(section: Any) -> Dict[str, Dict[str, Any]]:
    """Convert a JSON section into a mapping keyed by entity id."""

    result: Dict[str, Dict[str, Any]] = {}
    if isinstance(section, dict):
        for key, value in section.items():
            if isinstance(value, dict):
                value = dict(value)
                value.setdefault("id", key)
                result[value["id"]] = value
    elif isinstance(section, list):
        for entry in section:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id") or entry.get("name")
            if not entry_id:
                continue
            entry = dict(entry)
            entry.setdefault("id", entry_id)
            result[entry_id] = entry
    return result


def _load_identity_profiles() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load appearance profiles from disk."""

    if not IDENTITIES_PATH.exists():
        return {"person": {}, "object": {}, "unknown": {}}

    try:
        with IDENTITIES_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"person": {}, "object": {}, "unknown": {}}

    sections: Dict[str, Dict[str, Dict[str, Any]]] = {"person": {}, "object": {}, "unknown": {}}
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalised_key = (key or "unknown").lower()
            target: Dict[str, Dict[str, Any]]
            if normalised_key in {"person", "persons", "people", "humans"}:
                target = sections["person"]
            elif normalised_key in {"object", "objects", "items"}:
                target = sections["object"]
            else:
                target = sections["unknown"]
            target.update(_normalise_section(value))
    elif isinstance(payload, list):
        sections["unknown"].update(_normalise_section(payload))

    return sections


IDENTITY_PROFILES = _load_identity_profiles()


def resolve_identity(entity: GeminiEntity) -> Tuple[str, Dict[str, Any]]:
    """Resolve the identity of an entity using the appearance profiles."""

    entity_type = (entity.type or "unknown").lower()
    buckets: Iterable[Tuple[str, Dict[str, Dict[str, Any]]]] = (
        ("person", IDENTITY_PROFILES.get("person", {})),
        ("object", IDENTITY_PROFILES.get("object", {})),
        ("unknown", IDENTITY_PROFILES.get("unknown", {})),
    )

    preferred_bucket: Dict[str, Dict[str, Any]] = IDENTITY_PROFILES.get("unknown", {})
    canonical_type = "unknown"
    for bucket_name, bucket in buckets:
        if entity_type.startswith(bucket_name[:3]):
            preferred_bucket = bucket
            canonical_type = bucket_name
            break
    else:
        canonical_type = entity_type or "unknown"

    if entity.entity_id and entity.entity_id in preferred_bucket:
        profile = dict(preferred_bucket[entity.entity_id])
        profile.setdefault("type", canonical_type)
        return entity.entity_id, profile

    if entity.name:
        lookup = entity.name.lower()
        for bucket in (preferred_bucket, IDENTITY_PROFILES.get("person", {}), IDENTITY_PROFILES.get("object", {})):
            for profile_id, profile in bucket.items():
                if profile.get("name", "").lower() == lookup:
                    result = dict(profile)
                    result.setdefault("type", canonical_type)
                    return profile_id, result

    appearance = entity.appearance or {}
    attributes = entity.attributes or {}
    best_match: Optional[Tuple[str, Dict[str, Any]]] = None
    best_score = 0

    def score_profile(profile: Dict[str, Any]) -> int:
        score = 0
        profile_appearance = profile.get("appearance") or {}
        for key, value in appearance.items():
            profile_value = profile_appearance.get(key)
            if profile_value is None:
                continue
            if isinstance(value, list) and isinstance(profile_value, list):
                overlap = set(map(str, value)) & set(map(str, profile_value))
                score += len(overlap)
            elif isinstance(value, list):
                score += 1 if str(profile_value) in {str(item) for item in value} else 0
            elif isinstance(profile_value, list):
                score += 1 if str(value) in {str(item) for item in profile_value} else 0
            else:
                score += 1 if str(value).lower() == str(profile_value).lower() else 0
        profile_attributes = profile.get("attributes") or {}
        for key, value in attributes.items():
            if key in profile_attributes and profile_attributes[key] == value:
                score += 1
        return score

    for bucket in (preferred_bucket, IDENTITY_PROFILES.get("person", {}), IDENTITY_PROFILES.get("object", {})):
        for profile_id, profile in bucket.items():
            score = score_profile(profile)
            if score > best_score and score > 0:
                best_score = score
                best_match = (profile_id, dict(profile))

    if best_match:
        profile_id, profile = best_match
        profile.setdefault("type", canonical_type)
        return profile_id, profile

    generated_id = entity.entity_id
    if not generated_id:
        base = (entity.name or entity.type or canonical_type or "entity").strip() or "entity"
        slug = "_".join(base.lower().split())
        generated_id = f"{slug}_{uuid4().hex[:8]}"

    profile = {
        "id": generated_id,
        "name": entity.name,
        "type": canonical_type or entity.type or "unknown",
        "appearance": appearance,
        "attributes": attributes,
    }
    return generated_id, profile


def _build_event_actor(entity: GeminiEntity) -> EventActor:
    entity_id, profile = resolve_identity(entity)
    appearance: Dict[str, Any] = {}
    attributes: Dict[str, Any] = {}
    appearance.update(profile.get("appearance") or {})
    appearance.update(entity.appearance or {})
    attributes.update(profile.get("attributes") or {})
    attributes.update(entity.attributes or {})
    return EventActor(
        entity_id=entity_id,
        name=profile.get("name") or entity.name,
        type=profile.get("type") or entity.type or "unknown",
        appearance=appearance,
        attributes=attributes,
    )


def _update_world_state(state: SceneState, event: Event) -> None:
    for participant in filter(None, (event.actor, event.target)):
        existing = state.world_state.get(participant.entity_id)
        if existing is None:
            state.world_state[participant.entity_id] = EntityState(
                entity_id=participant.entity_id,
                name=participant.name,
                type=participant.type,
                appearance=dict(participant.appearance),
                attributes=dict(participant.attributes),
                last_event_id=event.id,
                last_updated=event.timestamp,
            )
            continue
        if participant.name:
            existing.name = participant.name
        if participant.type:
            existing.type = participant.type
        if participant.appearance:
            existing.appearance.update(participant.appearance)
        if participant.attributes:
            existing.attributes.update(participant.attributes)
        existing.last_event_id = event.id
        existing.last_updated = event.timestamp


def ingest(gemini_json: Dict[str, Any]) -> SceneState:
    """Ingest a Gemini payload, updating and persisting the scene state."""

    try:
        payload = GeminiPayload.parse_obj(gemini_json)
    except ValidationError as exc:
        raise ValueError(f"Invalid Gemini payload: {exc}") from exc

    state = state_store.load_state()
    existing_ids = {entry.id for entry in state.timeline}

    ordered_events = sorted(payload.events, key=lambda entry: entry.timestamp)
    for index, raw_event in enumerate(ordered_events):
        event_id = raw_event.event_id or f"event-{raw_event.timestamp.isoformat()}-{index}"
        while event_id in existing_ids:
            event_id = f"{event_id}-{uuid4().hex[:4]}"
        existing_ids.add(event_id)

        metadata: Dict[str, Any] = {}
        metadata.update(payload.metadata)
        metadata.update(raw_event.metadata)

        action = raw_event.action or raw_event.metadata.get("action") or "observation"

        actor = _build_event_actor(raw_event.actors[0]) if raw_event.actors else None
        target = _build_event_actor(raw_event.targets[0]) if raw_event.targets else None

        event = Event(
            id=event_id,
            timestamp=raw_event.timestamp,
            action=action,
            summary=raw_event.summary,
            actor=actor,
            target=target,
            metadata=metadata,
        )

        state.timeline.append(event)
        _update_world_state(state, event)

    state.timeline.sort(key=lambda entry: entry.timestamp)
    state_store.save_state(state)
    return state
