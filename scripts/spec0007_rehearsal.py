"""Seed and verify spec 0007 against an isolated live Mongo/Chroma stack."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Blue_dream_agents.consolidator import assess_event_importance
from Blue_dream_agents.db_client import close_mongo_client, get_mongo_client
from Blue_dream_agents.memory_schema import MemoryEvent, memory_event_to_mongo
from Blue_dream_agents.semantic_search import (
    close_clients,
    ensure_semantic_index_synced,
    run_semantic_retrieval,
)
from Blue_dream_agents.time_agent import _get_events
from Blue_dream_agents.timezone_utils import LOCAL_TZ, now_local
from Blue_dream_agents.vector_store import list_indexed_event_ids


LOW_IDS = ["spec0007-low-1", "spec0007-low-2", "spec0007-low-3"]
SURVIVOR_ID = "spec0007-pinned-survivor"
STALE_ID = "spec0007-stale-mug"
FRESH_ID = "spec0007-fresh-mug"


def summary_day() -> dt.date:
    return now_local().date() - dt.timedelta(days=4)


def summary_id() -> str:
    return f"sum_{summary_day().isoformat()}_0"


def make_event(
    event_id: str,
    timestamp: dt.datetime,
    semantic_text: str,
    *,
    room_number: int,
    room_name: str,
    importance: float,
    pinned: bool = False,
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id,
        timestamp=timestamp,
        room_number=room_number,
        room_name=room_name,
        semantic_text=semantic_text,
        video_description=semantic_text,
        importance=importance,
        importance_reason="isolated spec 0007 rehearsal fixture",
        pinned=pinned,
    )


async def seed() -> dict:
    database = get_mongo_client().dementia_assistance
    await database.events.delete_many({})
    await database.memory_summaries.delete_many({})
    await database.profile_facts.delete_many({})

    day = summary_day()
    mundane = [
        make_event(
            LOW_IDS[0],
            dt.datetime.combine(day, dt.time(9), tzinfo=LOCAL_TZ),
            "You quietly sorted books and read the morning newspaper in the bedroom.",
            room_number=0,
            room_name="Bedroom",
            importance=0.2,
        ),
        make_event(
            LOW_IDS[1],
            dt.datetime.combine(day, dt.time(10), tzinfo=LOCAL_TZ),
            "You made a cup of tea and returned to the bedroom to read.",
            room_number=0,
            room_name="Bedroom",
            importance=0.2,
        ),
        make_event(
            LOW_IDS[2],
            dt.datetime.combine(day, dt.time(11), tzinfo=LOCAL_TZ),
            "You watered the bedroom plant and put the newspaper away.",
            room_number=0,
            room_name="Bedroom",
            importance=0.2,
        ),
    ]
    survivor = make_event(
        SURVIVOR_ID,
        dt.datetime.combine(day, dt.time(12), tzinfo=LOCAL_TZ),
        "Your daughter Sarah visited you in the bedroom and shared lunch.",
        room_number=0,
        room_name="Bedroom",
        importance=0.2,
        pinned=True,
    )
    now = now_local()
    stale = make_event(
        STALE_ID,
        now - dt.timedelta(days=90),
        "Blue ceramic mug location: the blue ceramic mug was on the dining table.",
        room_number=1,
        room_name="Living Room",
        importance=0.5,
    )
    fresh = make_event(
        FRESH_ID,
        now - dt.timedelta(hours=1),
        "This morning you placed your blue cup beside the kettle in the living room.",
        room_number=1,
        room_name="Living Room",
        importance=0.5,
    )
    await database.events.insert_many(
        [memory_event_to_mongo(item) for item in [*mundane, survivor, stale, fresh]]
    )
    status = await ensure_semantic_index_synced(force_rebuild=True)
    return {
        "seeded_events": 6,
        "summary_day": day.isoformat(),
        "expected_summary_id": summary_id(),
        "index_status": status,
    }


async def verify() -> dict:
    database = get_mongo_client().dementia_assistance
    summary = await database.memory_summaries.find_one({"summary_id": summary_id()})
    if summary is None or set(summary.get("source_event_ids", [])) != set(LOW_IDS):
        raise AssertionError("Expected deterministic summary with all mundane sources")

    source_docs = {
        item["event_id"]: item
        async for item in database.events.find({"event_id": {"$in": LOW_IDS}})
    }
    if source_docs[LOW_IDS[0]].get("lifecycle_status") != "active":
        raise AssertionError("Pinned consolidated event was not reactivated")
    if not source_docs[LOW_IDS[0]].get("pinned"):
        raise AssertionError("Reactivated event was not pinned")
    if any(
        source_docs[event_id].get("lifecycle_status") != "consolidated"
        for event_id in LOW_IDS[1:]
    ):
        raise AssertionError("Unpinned summary sources were not consolidated")

    indexed_ids = set(list_indexed_event_ids())
    expected_indexed = {LOW_IDS[0], SURVIVOR_ID, STALE_ID, FRESH_ID, summary_id()}
    if indexed_ids != expected_indexed:
        raise AssertionError(
            f"Index mismatch: expected {sorted(expected_indexed)}, got {sorted(indexed_ids)}"
        )

    summary_result = await run_semantic_retrieval(
        "What do you remember about my quiet reading and tea in the bedroom?"
    )
    debug_ids = [item.id for item in summary_result.recall_debug.memories]
    if summary_id() not in debug_ids:
        raise AssertionError("Consolidated summary was not recallable")
    if LOW_IDS[0] not in debug_ids or SURVIVOR_ID not in debug_ids:
        raise AssertionError("Pinned events were not guaranteed in recall")

    stale_result = await run_semantic_retrieval("Where is my blue ceramic mug located?")
    by_id = {match.event_id: match for match in stale_result.matches}
    if STALE_ID not in by_id or FRESH_ID not in by_id:
        raise AssertionError("Stale/fresh rehearsal memories were not both considered")
    if not by_id[STALE_ID].score > by_id[FRESH_ID].score:
        raise AssertionError("Fixture did not produce the intended older higher similarity")
    if not by_id[FRESH_ID].final_score > by_id[STALE_ID].final_score:
        raise AssertionError("Fresh memory did not outrank the stale higher-similarity memory")

    day_start = dt.datetime.combine(summary_day(), dt.time.min, tzinfo=LOCAL_TZ)
    raw_time_events = await _get_events(
        day_start, day_start + dt.timedelta(days=1), room_number=0
    )
    raw_ids = {item.event_id for item in raw_time_events}
    if not set(LOW_IDS).issubset(raw_ids):
        raise AssertionError("Time-agent Mongo query lost consolidated raw events")

    fall_fixture = make_event(
        "importance-live-check",
        now_local(),
        "The patient fell beside the bed and may need medical help.",
        room_number=0,
        room_name="Bedroom",
        importance=0.5,
    )
    fall_fixture.danger_candidate = True
    fall_fixture.observed_hazards = ["possible fall"]
    assessment = await assess_event_importance(fall_fixture)
    if assessment.importance < 0.7:
        raise AssertionError("Live importance rubric did not score a fall as high importance")

    return {
        "summary_id": summary_id(),
        "summary_source_count": len(summary["source_event_ids"]),
        "active_index_ids": sorted(indexed_ids),
        "summary_recall": True,
        "pinned_recall": True,
        "stale_similarity": by_id[STALE_ID].score,
        "stale_final_score": by_id[STALE_ID].final_score,
        "fresh_similarity": by_id[FRESH_ID].score,
        "fresh_final_score": by_id[FRESH_ID].final_score,
        "fresh_outranks_stale": True,
        "time_agent_raw_event_count": len(raw_time_events),
        "live_fall_importance": assessment.importance,
    }


async def main(mode: str) -> None:
    try:
        result = await (seed() if mode == "seed" else verify())
        print(json.dumps(result, indent=2, default=str))
    finally:
        await close_clients()
        await close_mongo_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "verify"))
    args = parser.parse_args()
    asyncio.run(main(args.mode))
