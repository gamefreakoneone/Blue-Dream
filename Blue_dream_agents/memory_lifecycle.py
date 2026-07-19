from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from .db_client import get_events_collection, get_memory_summaries_collection
from .llm.client import invoke_structured
from .llm.model_registry import get_model_registry
from .llm.settings import get_provider_settings
from .memory_schema import MemoryEvent, memory_event_from_mongo
from .prompt_budget import compact_json_records, truncate_text
from .semantic_search import (
    delete_memory_embeddings,
    index_memory_event,
    index_memory_summary,
)
from .timezone_utils import LOCAL_TZ, now_local


logger = logging.getLogger(__name__)
CONSOLIDATION_PROMPT_BUDGET_CHARS = 14_000


class ConsolidationSummaryText(BaseModel):
    text: str = Field(min_length=1)


class ConsolidationFailure(BaseModel):
    summary_id: str
    date: str
    room_number: int
    reason: str


class ConsolidationSkip(BaseModel):
    date: str
    room_number: int
    remaining_event_count: int
    reason: str


class ConsolidationReport(BaseModel):
    groups_formed: int = 0
    events_consolidated: int = 0
    summaries_created: int = 0
    failures: list[ConsolidationFailure] = Field(default_factory=list)
    skipped: list[ConsolidationSkip] = Field(default_factory=list)


def _local_day_start(value: dt.datetime) -> dt.datetime:
    local = value.astimezone(LOCAL_TZ) if value.tzinfo else value.replace(tzinfo=LOCAL_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _event_id_query(event_ids: list[str]) -> dict[str, Any]:
    object_ids = [ObjectId(value) for value in event_ids if ObjectId.is_valid(value)]
    clauses: list[dict[str, Any]] = [{"event_id": {"$in": event_ids}}]
    if object_ids:
        clauses.append({"_id": {"$in": object_ids}})
    return {"$or": clauses}


async def _eligible_events(now: dt.datetime) -> list[MemoryEvent]:
    settings = get_provider_settings()
    cutoff = _local_day_start(now) - dt.timedelta(days=settings.consolidation_age_days)
    events: list[MemoryEvent] = []
    async for document in get_events_collection().find({"timestamp": {"$lt": cutoff}}):
        event = memory_event_from_mongo(document)
        if (
            event.lifecycle_status == "active"
            and not event.pinned
            and event.importance < settings.consolidation_importance_max
        ):
            events.append(event)
    return events


def _group_events(events: list[MemoryEvent]) -> dict[tuple[dt.date, int], list[MemoryEvent]]:
    grouped: dict[tuple[dt.date, int], list[MemoryEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.timestamp.astimezone(LOCAL_TZ).date(), event.room_number)].append(event)
    for group in grouped.values():
        group.sort(key=lambda item: (item.timestamp, item.event_id))
    return dict(grouped)


def _summary_prompt_records(events: list[MemoryEvent]) -> list[dict[str, Any]]:
    available = max(120, (CONSOLIDATION_PROMPT_BUDGET_CHARS - 1000) // len(events))
    records = [
        {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "memory": truncate_text(event.semantic_text, available),
        }
        for event in events
    ]
    return compact_json_records(records, max_chars=CONSOLIDATION_PROMPT_BUDGET_CHARS)


async def _generate_summary(
    *, summary_id: str, day: dt.date, room_number: int, room_name: str, events: list[MemoryEvent]
) -> dict[str, Any]:
    records = _summary_prompt_records(events)
    if len(records) != len(events):
        raise ValueError("consolidation prompt budget could not represent every source event")
    result = await invoke_structured(
        prompt={
            "date": day.isoformat(),
            "room_number": room_number,
            "room_name": room_name,
            "events": records,
        },
        output_model=ConsolidationSummaryText,
        system_prompt=(
            "Practice memory hygiene so the patient never has to. Consolidate these "
            "mundane memories into a concise, factual day-level memory. Preserve "
            "useful activities, objects, speech, and uncertainty. Do not invent "
            "details. The raw memories remain archived and are never erased."
        ),
        model_id=get_model_registry().synthesis,
        structured_output_prompt="Return one concise summary in the text field.",
        max_tokens=500,
    )
    return {
        "summary_id": summary_id,
        "period": "day",
        "date": day.isoformat(),
        "room_number": room_number,
        "room_name": room_name,
        "text": result.text.strip(),
        "source_event_ids": [event.event_id for event in events],
        "created_at": now_local(),
    }


async def _get_or_create_summary(
    *, summary_id: str, day: dt.date, room_number: int, events: list[MemoryEvent]
) -> tuple[dict[str, Any], bool]:
    collection = get_memory_summaries_collection()
    existing = await collection.find_one({"summary_id": summary_id})
    event_ids = {event.event_id for event in events}
    if existing is not None:
        if event_ids.issubset(set(existing.get("source_event_ids", []))):
            return existing, False
        raise ValueError("existing summary does not cover the active source events")

    document = await _generate_summary(
        summary_id=summary_id,
        day=day,
        room_number=room_number,
        room_name=events[0].room_name,
        events=events,
    )
    try:
        await collection.insert_one(document)
        return document, True
    except DuplicateKeyError:
        existing = await collection.find_one({"summary_id": summary_id})
        if existing is None:
            raise
        return existing, False


async def _existing_group_summaries(
    *, day: dt.date, room_number: int
) -> list[dict[str, Any]]:
    collection = get_memory_summaries_collection()
    return [
        document
        async for document in collection.find(
            {"date": day.isoformat(), "room_number": room_number}
        )
    ]


def _next_summary_id(
    *, day: dt.date, room_number: int, existing: list[dict[str, Any]]
) -> str:
    base_id = f"sum_{day.isoformat()}_{room_number}"
    used_ids = {str(document.get("summary_id")) for document in existing}
    if base_id not in used_ids:
        return base_id
    suffix = 1
    while f"{base_id}_{suffix}" in used_ids:
        suffix += 1
    return f"{base_id}_{suffix}"


async def run_consolidation(now: dt.datetime | None = None) -> ConsolidationReport:
    """Consolidate eligible day/room groups without deleting MongoDB memories."""

    current = now or now_local()
    settings = get_provider_settings()
    grouped = _group_events(await _eligible_events(current))
    qualifying = [
        (key, events)
        for key, events in sorted(grouped.items())
        if len(events) >= settings.consolidation_min_events
    ]
    report = ConsolidationReport(groups_formed=len(qualifying))

    for (day, room_number), events in qualifying:
        summary_id = f"sum_{day.isoformat()}_{room_number}"
        try:
            existing_summaries = await _existing_group_summaries(
                day=day, room_number=room_number
            )
            covered_event_ids = {
                str(event_id)
                for summary in existing_summaries
                for event_id in summary.get("source_event_ids", [])
            }
            new_events = [
                event for event in events if event.event_id not in covered_event_ids
            ]
            if existing_summaries and len(new_events) < settings.consolidation_min_events:
                report.skipped.append(
                    ConsolidationSkip(
                        date=day.isoformat(),
                        room_number=room_number,
                        remaining_event_count=len(new_events),
                        reason=(
                            "fewer than CONSOLIDATION_MIN_EVENTS remain after "
                            "excluding already summarized events"
                        ),
                    )
                )
                continue

            summary_id = _next_summary_id(
                day=day,
                room_number=room_number,
                existing=existing_summaries,
            )
            summary, created = await _get_or_create_summary(
                summary_id=summary_id,
                day=day,
                room_number=room_number,
                events=new_events,
            )
            event_ids = [event.event_id for event in new_events]
            await index_memory_summary(summary)
            await delete_memory_embeddings(event_ids)
            await get_events_collection().update_many(
                _event_id_query(event_ids),
                {
                    "$set": {
                        "lifecycle_status": "consolidated",
                        "consolidated_into": summary_id,
                    }
                },
            )
            report.events_consolidated += len(event_ids)
            report.summaries_created += int(created)
        except Exception:
            logger.exception("Consolidation failed for group %s", summary_id)
            report.failures.append(
                ConsolidationFailure(
                    summary_id=summary_id,
                    date=day.isoformat(),
                    room_number=room_number,
                    reason="group consolidation failed",
                )
            )
    return report


async def pin_event(event_id: str) -> bool:
    collection = get_events_collection()
    document = await collection.find_one(_event_id_query([event_id]))
    if document is None:
        return False
    event = memory_event_from_mongo(document)
    event.pinned = True
    event.lifecycle_status = "active"
    event.consolidated_into = None
    await collection.update_one(
        _event_id_query([event.event_id]),
        {
            "$set": {
                "pinned": True,
                "lifecycle_status": "active",
                "consolidated_into": None,
            }
        },
    )
    await index_memory_event(event)
    return True


async def unpin_event(event_id: str) -> bool:
    result = await get_events_collection().update_one(
        _event_id_query([event_id]),
        {"$set": {"pinned": False}},
    )
    return bool(result.matched_count)
