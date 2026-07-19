import asyncio
import copy
import datetime as dt
from types import SimpleNamespace

import pytest

from Blue_dream_agents import consolidator, memory_lifecycle, semantic_search
from Blue_dream_agents.memory_schema import (
    MemoryEvent,
    memory_event_from_mongo,
    memory_event_to_mongo,
)
from Blue_dream_agents.safety_agent import SafetyAssessment
from Blue_dream_agents.timezone_utils import LOCAL_TZ


def run(coro):
    return asyncio.run(coro)


def nested(document, path):
    value = document
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(document, clause) for clause in expected):
                return False
            continue
        actual = nested(document, key)
        if isinstance(expected, dict):
            if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, documents):
        self.documents = copy.deepcopy(documents)

    def sort(self, field, direction=None):
        self.documents.sort(key=lambda item: nested(item, field) or "", reverse=direction == -1)
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(list(documents or []))
        self.updates = []

    def find(self, query=None, projection=None):
        query = query or {}
        return FakeCursor([item for item in self.documents if matches(item, query)])

    async def find_one(self, query):
        return next((copy.deepcopy(item) for item in self.documents if matches(item, query)), None)

    async def insert_one(self, document):
        self.documents.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("summary_id"))

    async def update_many(self, query, update):
        count = 0
        for document in self.documents:
            if matches(document, query):
                document.update(copy.deepcopy(update.get("$set", {})))
                count += 1
        self.updates.append((copy.deepcopy(query), copy.deepcopy(update)))
        return SimpleNamespace(matched_count=count, modified_count=count)

    async def update_one(self, query, update):
        result = await self.update_many(query, update)
        return SimpleNamespace(
            matched_count=min(result.matched_count, 1),
            modified_count=min(result.modified_count, 1),
        )


def event(identifier, day, *, room=0, importance=0.2, pinned=False, status="active"):
    return MemoryEvent(
        event_id=identifier,
        timestamp=dt.datetime.combine(day, dt.time(9), tzinfo=LOCAL_TZ),
        room_number=room,
        room_name=f"Room {room}",
        semantic_text=f"Memory {identifier}",
        importance=importance,
        pinned=pinned,
        lifecycle_status=status,
    )


def test_legacy_lifecycle_defaults_and_serialization():
    legacy = memory_event_from_mongo(
        {
            "event_id": "legacy",
            "timestamp": dt.datetime(2026, 7, 1, tzinfo=LOCAL_TZ),
            "room_number": 0,
        }
    )
    assert legacy.importance == 0.5
    assert legacy.pinned is False
    assert legacy.lifecycle_status == "active"
    assert legacy.consolidated_into is None

    legacy.importance = 0.8
    legacy.importance_reason = "medical event"
    legacy.pinned = True
    document = memory_event_to_mongo(legacy)
    assert document["importance"] == 0.8
    assert document["importance_reason"] == "medical event"
    assert document["pinned"] is True
    assert document["lifecycle_status"] == "active"


def test_importance_failure_defaults_and_safety_warning_auto_pins(monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(consolidator, "invoke_structured", fail)
    item = event("safety", dt.date(2026, 7, 18))
    safety = SafetyAssessment(warning_needed=True, severity="high")
    run(consolidator.apply_event_lifecycle(item, safety))
    assert item.importance == 0.5
    assert item.importance_reason == "scoring unavailable"
    assert item.pinned is True


def test_grouping_uses_local_day_and_room_boundaries():
    first = event("a", dt.date(2026, 7, 14), room=0)
    second = event("b", dt.date(2026, 7, 14), room=1)
    third = event("c", dt.date(2026, 7, 15), room=0)
    grouped = memory_lifecycle._group_events([third, second, first])
    assert set(grouped) == {
        (dt.date(2026, 7, 14), 0),
        (dt.date(2026, 7, 14), 1),
        (dt.date(2026, 7, 15), 0),
    }
    cutoff = memory_lifecycle._local_day_start(
        dt.datetime(2026, 7, 18, 22, tzinfo=LOCAL_TZ)
    ) - dt.timedelta(days=2)
    assert cutoff == dt.datetime(2026, 7, 16, tzinfo=LOCAL_TZ)


def test_eligible_filter_applies_threshold_status_pin_and_minimum(monkeypatch):
    old = dt.date(2026, 7, 10)
    documents = [
        memory_event_to_mongo(event("low", old, importance=0.49)),
        memory_event_to_mongo(event("boundary", old, importance=0.5)),
        memory_event_to_mongo(event("pin", old, importance=0.1, pinned=True)),
        memory_event_to_mongo(event("done", old, importance=0.1, status="consolidated")),
    ]
    collection = FakeCollection(documents)
    monkeypatch.setattr(memory_lifecycle, "get_events_collection", lambda: collection)
    eligible = run(
        memory_lifecycle._eligible_events(
            dt.datetime(2026, 7, 18, 12, tzinfo=LOCAL_TZ)
        )
    )
    assert [item.event_id for item in eligible] == ["low"]


def test_consolidation_success_and_minimum_skip(monkeypatch):
    day = dt.date(2026, 7, 10)
    qualifying = [event(f"a{i}", day, room=0) for i in range(3)]
    too_small = [event(f"b{i}", day, room=1) for i in range(2)]
    events_collection = FakeCollection(
        [memory_event_to_mongo(item) for item in [*qualifying, *too_small]]
    )
    summary = {
        "summary_id": "sum_2026-07-10_0",
        "period": "day",
        "date": "2026-07-10",
        "room_number": 0,
        "room_name": "Room 0",
        "text": "A quiet morning.",
        "source_event_ids": [item.event_id for item in qualifying],
        "created_at": dt.datetime(2026, 7, 18, tzinfo=LOCAL_TZ),
    }
    calls = []

    async def eligible(now):
        return [*qualifying, *too_small]

    async def existing(**kwargs):
        return summary, True

    async def index(value):
        calls.append(("index", value["summary_id"]))

    async def delete(ids):
        calls.append(("delete", ids))

    monkeypatch.setattr(memory_lifecycle, "_eligible_events", eligible)
    monkeypatch.setattr(memory_lifecycle, "_get_or_create_summary", existing)
    monkeypatch.setattr(
        memory_lifecycle,
        "get_memory_summaries_collection",
        lambda: FakeCollection(),
    )
    monkeypatch.setattr(memory_lifecycle, "index_memory_summary", index)
    monkeypatch.setattr(memory_lifecycle, "delete_memory_embeddings", delete)
    monkeypatch.setattr(memory_lifecycle, "get_events_collection", lambda: events_collection)

    report = run(memory_lifecycle.run_consolidation())
    assert report.groups_formed == 1
    assert report.events_consolidated == 3
    assert report.summaries_created == 1
    assert calls[0] == ("index", "sum_2026-07-10_0")
    assert all(doc["lifecycle_status"] == "consolidated" for doc in events_collection.documents[:3])
    assert all(doc["lifecycle_status"] == "active" for doc in events_collection.documents[3:])


def test_consolidation_isolates_one_group_failure(monkeypatch):
    day = dt.date(2026, 7, 10)
    items = [event(f"r{room}-{i}", day, room=room) for room in (0, 1) for i in range(3)]
    collection = FakeCollection([memory_event_to_mongo(item) for item in items])

    async def eligible(now):
        return items

    async def create(*, room_number, **kwargs):
        if room_number == 0:
            raise RuntimeError("sentinel")
        return {
            "summary_id": "sum_2026-07-10_1",
            "date": "2026-07-10",
            "room_number": 1,
            "room_name": "Room 1",
            "text": "summary",
        }, True

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(memory_lifecycle, "_eligible_events", eligible)
    monkeypatch.setattr(memory_lifecycle, "_get_or_create_summary", create)
    monkeypatch.setattr(
        memory_lifecycle,
        "get_memory_summaries_collection",
        lambda: FakeCollection(),
    )
    monkeypatch.setattr(memory_lifecycle, "index_memory_summary", noop)
    monkeypatch.setattr(memory_lifecycle, "delete_memory_embeddings", noop)
    monkeypatch.setattr(memory_lifecycle, "get_events_collection", lambda: collection)
    report = run(memory_lifecycle.run_consolidation())
    assert report.groups_formed == 2
    assert report.events_consolidated == 3
    assert report.summaries_created == 1
    assert report.failures[0].summary_id == "sum_2026-07-10_0"
    assert report.failures[0].reason == "group consolidation failed"


def test_reactivated_source_with_too_few_late_events_is_skipped(monkeypatch):
    day = dt.date(2026, 7, 10)
    old_source = event("old-a", day, status="consolidated")
    old_source.consolidated_into = "sum_2026-07-10_0"
    late_events = [event(f"late-{index}", day) for index in range(2)]
    events_collection = FakeCollection(
        [memory_event_to_mongo(item) for item in [old_source, *late_events]]
    )
    summaries_collection = FakeCollection(
        [
            {
                "summary_id": "sum_2026-07-10_0",
                "date": day.isoformat(),
                "room_number": 0,
                "source_event_ids": ["old-a", "old-b", "old-c"],
            }
        ]
    )

    async def noop(*args, **kwargs):
        return None

    async def forbidden(*args, **kwargs):
        raise AssertionError("skipped groups must not mutate the index")

    settings = SimpleNamespace(
        consolidation_age_days=2,
        consolidation_importance_max=0.5,
        consolidation_min_events=3,
    )
    monkeypatch.setattr(memory_lifecycle, "get_provider_settings", lambda: settings)
    monkeypatch.setattr(
        memory_lifecycle, "get_events_collection", lambda: events_collection
    )
    monkeypatch.setattr(
        memory_lifecycle,
        "get_memory_summaries_collection",
        lambda: summaries_collection,
    )
    monkeypatch.setattr(memory_lifecycle, "index_memory_event", noop)
    monkeypatch.setattr(memory_lifecycle, "index_memory_summary", forbidden)
    monkeypatch.setattr(memory_lifecycle, "delete_memory_embeddings", forbidden)

    assert run(memory_lifecycle.pin_event("old-a")) is True
    assert run(memory_lifecycle.unpin_event("old-a")) is True
    report = run(
        memory_lifecycle.run_consolidation(
            dt.datetime(2026, 7, 18, 12, tzinfo=LOCAL_TZ)
        )
    )

    assert report.groups_formed == 1
    assert report.events_consolidated == 0
    assert report.summaries_created == 0
    assert report.failures == []
    assert len(report.skipped) == 1
    assert report.skipped[0].remaining_event_count == 2
    assert all(
        document["lifecycle_status"] == "active"
        for document in events_collection.documents
    )


def test_late_events_use_suffixed_summary_and_rerun_is_no_op(monkeypatch):
    day = dt.date(2026, 7, 10)
    old_source = event("old-a", day, status="consolidated")
    old_source.consolidated_into = "sum_2026-07-10_0"
    late_events = [event(f"late-{index}", day) for index in range(3)]
    events_collection = FakeCollection(
        [memory_event_to_mongo(item) for item in [old_source, *late_events]]
    )
    summaries_collection = FakeCollection(
        [
            {
                "summary_id": "sum_2026-07-10_0",
                "date": day.isoformat(),
                "room_number": 0,
                "source_event_ids": ["old-a", "old-b", "old-c"],
            }
        ]
    )
    index_calls = []
    delete_calls = []

    async def generate(*, summary_id, day, room_number, room_name, events):
        return {
            "summary_id": summary_id,
            "period": "day",
            "date": day.isoformat(),
            "room_number": room_number,
            "room_name": room_name,
            "text": "Late memories.",
            "source_event_ids": [item.event_id for item in events],
            "created_at": dt.datetime(2026, 7, 18, tzinfo=LOCAL_TZ),
        }

    async def index_event(value):
        index_calls.append(("event", value.event_id))

    async def index_summary(value):
        index_calls.append(("summary", value["summary_id"]))

    async def delete(ids):
        delete_calls.append(list(ids))

    settings = SimpleNamespace(
        consolidation_age_days=2,
        consolidation_importance_max=0.5,
        consolidation_min_events=3,
    )
    monkeypatch.setattr(memory_lifecycle, "get_provider_settings", lambda: settings)
    monkeypatch.setattr(
        memory_lifecycle, "get_events_collection", lambda: events_collection
    )
    monkeypatch.setattr(
        memory_lifecycle,
        "get_memory_summaries_collection",
        lambda: summaries_collection,
    )
    monkeypatch.setattr(memory_lifecycle, "_generate_summary", generate)
    monkeypatch.setattr(memory_lifecycle, "index_memory_event", index_event)
    monkeypatch.setattr(memory_lifecycle, "index_memory_summary", index_summary)
    monkeypatch.setattr(memory_lifecycle, "delete_memory_embeddings", delete)

    assert run(memory_lifecycle.pin_event("old-a")) is True
    assert run(memory_lifecycle.unpin_event("old-a")) is True
    first = run(
        memory_lifecycle.run_consolidation(
            dt.datetime(2026, 7, 18, 12, tzinfo=LOCAL_TZ)
        )
    )

    suffixed = next(
        item
        for item in summaries_collection.documents
        if item["summary_id"] == "sum_2026-07-10_0_1"
    )
    assert suffixed["source_event_ids"] == ["late-0", "late-1", "late-2"]
    assert first.events_consolidated == 3
    assert first.summaries_created == 1
    assert first.skipped == []
    assert delete_calls == [["late-0", "late-1", "late-2"]]
    assert events_collection.documents[0]["lifecycle_status"] == "active"
    assert all(
        document["consolidated_into"] == "sum_2026-07-10_0_1"
        for document in events_collection.documents[1:]
    )

    calls_after_first = (list(index_calls), list(delete_calls))
    second = run(
        memory_lifecycle.run_consolidation(
            dt.datetime(2026, 7, 18, 12, tzinfo=LOCAL_TZ)
        )
    )
    assert second.groups_formed == 0
    assert second.events_consolidated == 0
    assert second.summaries_created == 0
    assert second.skipped == []
    assert (index_calls, delete_calls) == calls_after_first


def test_pin_reactivates_and_reembeds_while_unpin_stays_active(monkeypatch):
    item = event("pin-me", dt.date(2026, 7, 10), status="consolidated")
    item.consolidated_into = "sum_old"
    collection = FakeCollection([memory_event_to_mongo(item)])
    indexed = []

    async def index(value):
        indexed.append(value)

    monkeypatch.setattr(memory_lifecycle, "get_events_collection", lambda: collection)
    monkeypatch.setattr(memory_lifecycle, "index_memory_event", index)
    assert run(memory_lifecycle.pin_event("pin-me")) is True
    assert collection.documents[0]["pinned"] is True
    assert collection.documents[0]["lifecycle_status"] == "active"
    assert collection.documents[0]["consolidated_into"] is None
    assert indexed[0].event_id == "pin-me"
    assert run(memory_lifecycle.unpin_event("pin-me")) is True
    assert collection.documents[0]["pinned"] is False
    assert collection.documents[0]["lifecycle_status"] == "active"
    assert run(memory_lifecycle.pin_event("missing")) is False


def test_rebuild_indexes_active_and_legacy_events_plus_summaries(monkeypatch):
    day = dt.date(2026, 7, 10)
    active = memory_event_to_mongo(event("active", day))
    legacy = copy.deepcopy(active)
    legacy["event_id"] = "legacy"
    legacy.pop("lifecycle_status")
    consolidated = memory_event_to_mongo(event("done", day, status="consolidated"))
    summaries = FakeCollection(
        [{"summary_id": "sum", "date": "2026-07-10", "text": "summary"}]
    )
    database = SimpleNamespace(
        events=FakeCollection([active, legacy, consolidated]),
        memory_summaries=summaries,
    )
    captured = []

    async def index_event(value):
        captured.append(("event", value.event_id))

    async def index_summary(value):
        captured.append(("summary", value["summary_id"]))

    monkeypatch.setattr(
        semantic_search,
        "get_mongo_client",
        lambda: SimpleNamespace(dementia_assistance=database),
    )
    monkeypatch.setattr(semantic_search, "index_memory_event", index_event)
    monkeypatch.setattr(semantic_search, "index_memory_summary", index_summary)
    assert run(semantic_search._index_all_mongo_events()) is True
    assert captured == [("event", "active"), ("event", "legacy"), ("summary", "sum")]


def test_semantic_summary_hydration_and_recall_debug(monkeypatch):
    summary = {
        "summary_id": "sum_2026-07-10_0",
        "date": "2026-07-10",
        "room_number": 0,
        "room_name": "Bedroom",
        "text": "You read quietly in the bedroom.",
    }

    async def ready(*args, **kwargs):
        return "ready"

    async def embed(values):
        return [[0.1, 0.2]]

    async def blocking(func, *args):
        return func(*args)

    def query(embedding, top_k):
        return [
            {
                "memory_id": summary["summary_id"],
                "event_id": summary["summary_id"],
                "type": "summary",
                "distance": 0.25,
                "metadata": {"type": "summary"},
            }
        ]

    async def no_events(*args, **kwargs):
        return []

    async def summaries(ids):
        return [summary]

    async def facts():
        return [
            {
                "fact_id": "fact-pinned",
                "text": "Daughter is Sarah",
                "pinned": True,
                "created_at": "2026-07-01T09:00:00-07:00",
            }
        ]

    monkeypatch.setattr(semantic_search, "ensure_semantic_index_synced", ready)
    monkeypatch.setattr(semantic_search, "embed_texts", embed)
    monkeypatch.setattr(semantic_search, "_run_blocking", blocking)
    monkeypatch.setattr(semantic_search, "query_similar_embeddings", query)
    monkeypatch.setattr(semantic_search, "_fetch_events_by_ids", no_events)
    monkeypatch.setattr(semantic_search, "_fetch_summaries_by_ids", summaries)
    monkeypatch.setattr(semantic_search, "_fetch_pinned_events", no_events)
    monkeypatch.setattr(semantic_search, "get_active_facts", facts)

    result = run(semantic_search.run_semantic_retrieval("quiet reading"))
    assert result.success is True
    assert [match.memory_type for match in result.matches] == ["fact", "summary"]
    assert result.matches[1].timestamp.startswith("2026-07-10T00:00:00")
    assert result.recall_debug.considered_count == 2
    assert result.recall_debug.packed_count == 2
    assert result.recall_debug.memories[0].pinned is True


def test_lifecycle_endpoint_contracts(client, monkeypatch, api_module):
    async def report():
        return memory_lifecycle.ConsolidationReport(
            groups_formed=1, events_consolidated=3, summaries_created=1
        )

    async def known(identifier):
        return identifier == "known"

    monkeypatch.setattr(api_module, "run_consolidation", report)
    monkeypatch.setattr(api_module, "pin_event", known)
    monkeypatch.setattr(api_module, "unpin_event", known)
    payload = client.post("/memory/consolidate").json()
    assert payload["events_consolidated"] == 3
    assert client.post("/memory/events/known/pin").json() == {"ok": True}
    assert client.post("/memory/events/known/unpin").json() == {"ok": True}
    assert client.post("/memory/events/missing/pin").status_code == 404
