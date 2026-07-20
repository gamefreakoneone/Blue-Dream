import asyncio
import copy
import datetime as dt
from types import SimpleNamespace

from bson import ObjectId

from Blue_dream_agents import db_client, memory_digest
from Blue_dream_agents.memory_digest import DailyDigestService, DailyDigestText
from Blue_dream_agents.timezone_utils import LOCAL_TZ


def run(coro):
    return asyncio.run(coro)


def matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, documents):
        self.documents = copy.deepcopy(list(documents))

    def sort(self, field, direction):
        self.documents.sort(
            key=lambda item: (item.get(field) is None, item.get(field)),
            reverse=direction == -1,
        )
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class Collection:
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(list(documents or []))
        self.indexes = []

    async def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))
        return kwargs.get("name")

    async def find_one(self, query):
        return next(
            (copy.deepcopy(item) for item in self.documents if matches(item, query)),
            None,
        )

    def find(self, query):
        return Cursor(item for item in self.documents if matches(item, query))

    async def update_one(self, query, update, upsert=False):
        target = next((item for item in self.documents if matches(item, query)), None)
        inserted = target is None
        if inserted and upsert:
            target = copy.deepcopy(query)
            self.documents.append(target)
        if target is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        if inserted:
            target.update(copy.deepcopy(update.get("$setOnInsert", {})))
        target.update(copy.deepcopy(update.get("$set", {})))
        return SimpleNamespace(
            matched_count=0 if inserted else 1,
            modified_count=1,
        )


def event(event_id, timestamp, text, importance=0.5, status="active"):
    return {
        "_id": ObjectId(),
        "event_id": event_id,
        "timestamp": timestamp,
        "room_number": 1,
        "room_name": "Kitchen",
        "semantic_text": text,
        "importance": importance,
        "lifecycle_status": status,
    }


def service_for(*, events=None, summaries=None, digests=None):
    return DailyDigestService(
        events_collection=Collection(events),
        summaries_collection=Collection(summaries),
        digests_collection=Collection(digests),
    )


def test_generation_then_cache_hit_uses_zero_additional_llm_calls(
    monkeypatch, caplog
):
    now = dt.datetime(2026, 7, 20, 12, tzinfo=LOCAL_TZ)
    service = service_for(
        events=[event("event-1", now.replace(hour=9), "You made tea.")],
        summaries=[
            {
                "summary_id": "summary-1",
                "date": "2026-07-20",
                "room_number": 1,
                "room_name": "Kitchen",
                "text": "You had a calm morning.",
            }
        ],
    )
    calls = []

    async def structured(**kwargs):
        calls.append(kwargs["prompt"])
        return DailyDigestText(
            text=(
                "You had a calm morning. You made tea. "
                "It was a comfortable start to the day. Extra sentence. Hidden fifth."
            ),
            highlights=["Morning tea", "Calm start", "Morning tea", "Ignored"],
        )

    monkeypatch.setattr(memory_digest, "invoke_structured", structured)
    caplog.set_level("INFO", logger="Blue_dream_agents.memory_digest")

    first = run(service.get_digests(1, now=now))
    second = run(service.get_digests(1, now=now))

    assert first == second
    assert len(calls) == 1
    assert len(first[0]["text"].split(". ")) == 4
    assert first[0]["highlights"] == ["Morning tea", "Calm start", "Ignored"]
    assert first[0]["source_summary_count"] == 1
    assert first[0]["source_event_count"] == 1
    assert "Daily digest cache hit for 2026-07-20" in caplog.text
    assert set(first[0]) == set(memory_digest.PUBLIC_FIELDS)


def test_raw_event_fallback_without_summaries_reaches_prompt(monkeypatch):
    now = dt.datetime(2026, 7, 20, 12, tzinfo=LOCAL_TZ)
    service = service_for(
        events=[
            event("low", now.replace(hour=8), "You opened the curtains.", 0.2),
            event("high", now.replace(hour=10), "You spoke with Sarah.", 0.9),
            event(
                "consolidated",
                now.replace(hour=11),
                "This should not appear.",
                1.0,
                status="consolidated",
            ),
        ]
    )
    captured = {}

    async def structured(**kwargs):
        captured.update(kwargs["prompt"])
        return DailyDigestText(text="You spoke with Sarah and opened the curtains.")

    monkeypatch.setattr(memory_digest, "invoke_structured", structured)
    result = run(service.get_digests(1, now=now))

    assert result[0]["source_summary_count"] == 0
    assert result[0]["source_event_count"] == 2
    assert [item["event_id"] for item in captured["recent_moments"]] == [
        "high",
        "low",
    ]
    assert captured["memory_summaries"] == []
    assert "This should not appear" not in str(captured)


def test_fingerprint_change_and_force_regenerate(monkeypatch):
    now = dt.datetime(2026, 7, 20, 12, tzinfo=LOCAL_TZ)
    events = Collection(
        [event("event-1", now.replace(hour=9), "You made tea.")]
    )
    service = DailyDigestService(
        events_collection=events,
        summaries_collection=Collection(),
        digests_collection=Collection(),
    )
    calls = []

    async def structured(**kwargs):
        calls.append(kwargs["prompt"])
        return DailyDigestText(text=f"Digest generation {len(calls)}.")

    monkeypatch.setattr(memory_digest, "invoke_structured", structured)
    run(service.get_digests(1, now=now))
    events.documents.append(
        event("event-2", now.replace(hour=10), "You read a book.")
    )
    changed = run(service.get_digests(1, now=now))
    forced = run(service.get_digests(1, now=now, force=True))

    assert len(calls) == 3
    assert changed[0]["text"] == "Digest generation 2."
    assert forced[0]["text"] == "Digest generation 3."
    assert len(service.digests_collection.documents) == 1


def test_generation_failure_returns_stale_cache(monkeypatch):
    now = dt.datetime(2026, 7, 20, 12, tzinfo=LOCAL_TZ)
    stale_time = now - dt.timedelta(hours=1)
    service = service_for(
        events=[event("new-event", now.replace(hour=9), "You made tea.")],
        digests=[
            {
                "digest_id": "dig_2026-07-20",
                "date": "2026-07-20",
                "text": "A saved recap.",
                "highlights": [],
                "source_fingerprint": "stale",
                "source_summary_count": 1,
                "source_event_count": 0,
                "created_at": stale_time,
                "updated_at": stale_time,
            }
        ],
    )

    async def fail(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(memory_digest, "invoke_structured", fail)
    result = run(service.get_digests(1, now=now))

    assert result[0]["text"] == "A saved recap."
    assert result[0]["created_at"].endswith("-07:00")


def test_generation_failure_without_cache_omits_only_failed_day(monkeypatch):
    now = dt.datetime(2026, 7, 20, 12, tzinfo=LOCAL_TZ)
    service = service_for(
        events=[
            event("today", now.replace(hour=9), "Today happened."),
            event(
                "yesterday",
                (now - dt.timedelta(days=1)).replace(hour=9),
                "Yesterday happened.",
            ),
        ]
    )

    async def structured(**kwargs):
        if kwargs["prompt"]["date"] == "2026-07-20":
            raise RuntimeError("today failed")
        return DailyDigestText(text="Yesterday was remembered.")

    monkeypatch.setattr(memory_digest, "invoke_structured", structured)
    result = run(service.get_digests(2, now=now))

    assert [item["date"] for item in result] == ["2026-07-19"]


def test_digest_endpoint_contract_and_validation(client, monkeypatch, api_module):
    captured = {}

    async def digests(days, *, force=False):
        captured.update(days=days, force=force)
        return [
            {
                "digest_id": "dig_2026-07-20",
                "date": "2026-07-20",
                "text": "You had a gentle day.",
                "highlights": ["Tea with Sarah"],
                "source_summary_count": 1,
                "source_event_count": 2,
                "created_at": "2026-07-20T12:00:00-07:00",
                "updated_at": "2026-07-20T12:00:00-07:00",
            }
        ]

    monkeypatch.setattr(api_module, "get_daily_digests", digests)
    response = client.get("/memory/digest?days=7&force=true")

    assert response.status_code == 200
    assert response.json()["digests"][0]["digest_id"] == "dig_2026-07-20"
    assert captured == {"days": 7, "force": True}
    assert client.get("/memory/digest?days=0").status_code == 422
    assert client.get("/memory/digest?days=32").status_code == 422


def test_digest_date_index(monkeypatch):
    collection = Collection()
    monkeypatch.setattr(
        db_client,
        "get_memory_digests_collection",
        lambda: collection,
    )

    run(db_client.ensure_memory_digest_indexes())

    assert collection.indexes == [
        ([("date", 1)], {"name": "date_1", "unique": True})
    ]
