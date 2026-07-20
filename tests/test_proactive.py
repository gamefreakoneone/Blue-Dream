import asyncio
import copy
import datetime as dt
from types import SimpleNamespace

from pymongo.errors import DuplicateKeyError

from Blue_dream_agents import proactive_service
from Blue_dream_agents.memory_schema import MemoryEvent
from Blue_dream_agents.timezone_utils import LOCAL_TZ


def _nested(document, path):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(document, query):
    for key, expected in query.items():
        actual = _nested(document, key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


def _set_nested(document, path, value):
    target = document
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = copy.deepcopy(value)


class FakeCursor:
    def __init__(self, documents):
        self.documents = copy.deepcopy(documents)

    def sort(self, field_or_fields, direction=None):
        fields = field_or_fields if isinstance(field_or_fields, list) else [(field_or_fields, direction)]
        for field, sort_direction in reversed(fields):
            self.documents.sort(
                key=lambda item: (_nested(item, field) is None, _nested(item, field)),
                reverse=sort_direction == -1,
            )
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self.iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(list(documents or []))
        self.indexes = []
        self._lock = asyncio.Lock()

    async def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))
        return kwargs.get("name")

    async def insert_one(self, document):
        related_id = document.get("related_id")
        if related_id and any(item.get("related_id") == related_id for item in self.documents):
            raise DuplicateKeyError("duplicate related_id")
        self.documents.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("message_id"))

    async def find_one(self, query):
        match = next((item for item in self.documents if _matches(item, query)), None)
        return copy.deepcopy(match)

    def find(self, query):
        return FakeCursor([item for item in self.documents if _matches(item, query)])

    async def count_documents(self, query, limit=0):
        count = sum(_matches(item, query) for item in self.documents)
        return min(count, limit) if limit else count

    async def find_one_and_update(self, query, update, sort=None, return_document=None):
        async with self._lock:
            matches = [item for item in self.documents if _matches(item, query)]
            if sort:
                for field, direction in reversed(sort):
                    matches.sort(key=lambda item: _nested(item, field), reverse=direction == -1)
            if not matches:
                return None
            target = matches[0]
            for key, value in update.get("$set", {}).items():
                _set_nested(target, key, value)
            return copy.deepcopy(target)

    async def update_one(self, query, update, upsert=False):
        target = next((item for item in self.documents if _matches(item, query)), None)
        if target is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        for key, value in update.get("$set", {}).items():
            _set_nested(target, key, value)
        return SimpleNamespace(matched_count=1, modified_count=1)


def run(coro):
    return asyncio.run(coro)


def configure_message_store(monkeypatch, collection, now):
    async def noop_indexes():
        return None

    async def noop_push(document):
        return None

    monkeypatch.setattr(proactive_service, "initialize_proactive_indexes", noop_indexes)
    monkeypatch.setattr(
        proactive_service, "get_proactive_messages_collection", lambda: collection
    )
    monkeypatch.setattr(proactive_service, "now_local", lambda: now)
    monkeypatch.setattr(
        proactive_service.web_push, "send_for_proactive_message", noop_push
    )


def test_message_creation_dedupe_schema_and_stored_path(monkeypatch):
    now = dt.datetime(2026, 7, 18, 8, tzinfo=LOCAL_TZ)
    collection = FakeCollection()
    configure_message_store(monkeypatch, collection, now)

    first = run(
        proactive_service.create_message(
            trigger_type="safety",
            text="  Please   return to the kitchen. ",
            image_path="Storage/highlighted/stove.jpg",
            related_id="alert-1",
        )
    )
    second = run(
        proactive_service.create_message(
            trigger_type="safety",
            text="Duplicate",
            related_id="alert-1",
        )
    )

    assert first == second
    assert len(collection.documents) == 1
    message = collection.documents[0]
    assert message["message_id"].startswith("pm_")
    assert message["text"] == "Please return to the kitchen."
    assert message["image_path"] == "Storage/highlighted/stove.jpg"
    assert message["status"] == "pending"
    assert message["expires_at"] == now + dt.timedelta(minutes=60)


def test_expiry_atomic_delivery_and_idempotent_ack(monkeypatch):
    now = dt.datetime(2026, 7, 18, 8, tzinfo=LOCAL_TZ)
    collection = FakeCollection()
    configure_message_store(monkeypatch, collection, now)

    for index in range(3):
        run(
            proactive_service.create_message(
                trigger_type="reminder",
                text=f"Reminder {index}",
                related_id=f"r-{index}",
            )
        )
        collection.documents[-1]["created_at"] += dt.timedelta(seconds=index)
    expired_id = run(
        proactive_service.create_message(
            trigger_type="safety", text="Stale warning", related_id="expired"
        )
    )
    collection.documents[-1]["expires_at"] = now

    async def concurrent_polls():
        return await asyncio.gather(
            proactive_service.get_pending(now),
            proactive_service.get_pending(now),
        )

    first, second = run(concurrent_polls())
    claimed = [item for batch in (first, second) for item in batch]
    assert [item["text"] for item in claimed] == [
        "Reminder 0",
        "Reminder 1",
        "Reminder 2",
    ]
    assert len({item["message_id"] for item in claimed}) == 3
    assert next(item for item in collection.documents if item["message_id"] == expired_id)["status"] == "pending"
    assert run(proactive_service.get_pending(now)) == []

    message_id = claimed[0]["message_id"]
    assert run(proactive_service.acknowledge(message_id)) is True
    assert run(proactive_service.acknowledge(message_id)) is True
    assert run(proactive_service.acknowledge("missing")) is False


def test_due_reminders_materialize_then_roll_forward(monkeypatch):
    now = dt.datetime(2026, 7, 18, 9, tzinfo=LOCAL_TZ)
    collection = FakeCollection()
    configure_message_store(monkeypatch, collection, now)
    due = {
        "reminder_id": "daily-1",
        "text": "Take your morning medicine.",
        "due_at": now.isoformat(),
        "recurrence": "daily",
    }
    completed = []

    async def due_reminders(value):
        return [due]

    async def complete(reminder_id, *, mode, now=None):
        completed.append((reminder_id, mode, now))
        return True

    monkeypatch.setattr(proactive_service, "get_due_reminders", due_reminders)
    monkeypatch.setattr(proactive_service, "mark_done", complete)
    run(proactive_service.check_due_reminders(now))
    run(proactive_service.check_due_reminders(now))

    assert len(collection.documents) == 1
    assert completed == [
        ("daily-1", "delivery", now),
        ("daily-1", "delivery", now),
    ]
    assert collection.documents[0]["related_id"] == f"daily-1_{now.isoformat()}"


def test_morning_report_first_event_context_and_date_dedupe(monkeypatch):
    now = dt.datetime(2026, 7, 18, 7, tzinfo=LOCAL_TZ)
    messages = FakeCollection()
    events = FakeCollection([{"timestamp": now, "event_id": "first"}])
    summaries = FakeCollection(
        [{"date": "2026-07-17", "room_number": 0, "text": "You read with Sarah."}]
    )
    configure_message_store(monkeypatch, messages, now)
    monkeypatch.setattr(proactive_service, "get_events_collection", lambda: events)
    monkeypatch.setattr(
        proactive_service, "get_memory_summaries_collection", lambda: summaries
    )

    async def reminders():
        return [
            {"trigger_type": "time", "due_at": now.isoformat(), "text": "Take medicine"},
            {"trigger_type": "time", "due_at": (now + dt.timedelta(days=1)).isoformat(), "text": "Tomorrow"},
        ]

    async def facts():
        return [
            {"category": "safety", "text": "Use the handrail", "pinned": True},
            {"category": "preference", "text": "Likes tea", "pinned": True},
        ]

    prompts = []

    async def synthesize(**kwargs):
        prompts.append(kwargs["prompt"])
        return proactive_service.MorningReportText(
            text="Good morning. Yesterday you read with Sarah. Remember your medicine."
        )

    monkeypatch.setattr(proactive_service, "list_active_reminders", reminders)
    monkeypatch.setattr(proactive_service, "get_active_facts", facts)
    monkeypatch.setattr(proactive_service, "invoke_structured", synthesize)

    run(proactive_service.maybe_morning_report(now))
    run(proactive_service.maybe_morning_report(now))

    assert len(messages.documents) == 1
    assert messages.documents[0]["related_id"] == "morning_2026-07-18"
    assert prompts[0]["yesterday_memories"] == ["You read with Sarah."]
    assert prompts[0]["today_reminders"] == ["Take medicine"]
    assert prompts[0]["pinned_safety_facts"] == ["Use the handrail"]

    events.documents.append({"timestamp": now, "event_id": "second"})
    messages.documents.clear()
    run(proactive_service.maybe_morning_report(now))
    assert messages.documents == []


def test_morning_report_uses_quiet_fallback_at_local_date_boundary(monkeypatch):
    utc_timestamp = dt.datetime(2026, 7, 18, 7, 30, tzinfo=dt.timezone.utc)
    local_timestamp = utc_timestamp.astimezone(LOCAL_TZ)
    messages = FakeCollection()
    events = FakeCollection([{"timestamp": local_timestamp, "event_id": "first"}])
    configure_message_store(monkeypatch, messages, local_timestamp)
    monkeypatch.setattr(proactive_service, "get_events_collection", lambda: events)
    monkeypatch.setattr(
        proactive_service, "get_memory_summaries_collection", lambda: FakeCollection()
    )

    async def empty():
        return []

    prompts = []

    async def synthesize(**kwargs):
        prompts.append(kwargs["prompt"])
        return proactive_service.MorningReportText(
            text="Good morning. Yesterday was quiet. Take care today. Extra sentence."
        )

    monkeypatch.setattr(proactive_service, "list_active_reminders", empty)
    monkeypatch.setattr(proactive_service, "get_active_facts", empty)
    monkeypatch.setattr(proactive_service, "invoke_structured", synthesize)

    run(proactive_service.maybe_morning_report(utc_timestamp))
    assert messages.documents[0]["related_id"] == "morning_2026-07-18"
    assert messages.documents[0]["text"] == "Good morning. Yesterday was quiet. Take care today."
    assert prompts[0]["yesterday_memories"] == ["It was a quiet day yesterday."]


def _event(now):
    return MemoryEvent(
        event_id="event-1",
        timestamp=now,
        room_number=1,
        room_name="Living Room",
        semantic_text="You put on your shoes and left the living room.",
    )


def _event_reminder(valid_date=None):
    return {
        "reminder_id": "water-1",
        "text": "Please remember your water bottle.",
        "event_trigger": {
            "room_number": 1,
            "window_start": "06:00",
            "window_end": "11:00",
            "condition": "you put on shoes and leave",
            "valid_date": valid_date,
        },
    }


def test_event_reminder_llm_match_false_fallback_dedupe_and_rearm(monkeypatch):
    now = dt.datetime(2026, 7, 18, 8, tzinfo=LOCAL_TZ)
    messages = FakeCollection()
    configure_message_store(monkeypatch, messages, now)
    candidates = [_event_reminder()]
    completed = []

    async def matchable(value, *, room_number=None):
        assert room_number == 1
        return candidates

    async def complete(reminder_id, *, mode, now=None):
        completed.append(reminder_id)
        return True

    decisions = [True, True]

    async def judge(**kwargs):
        return proactive_service.EventReminderMatch(matches=decisions.pop(0), reason="test")

    monkeypatch.setattr(proactive_service, "get_matchable_event_reminders", matchable)
    monkeypatch.setattr(proactive_service, "mark_done", complete)
    monkeypatch.setattr(proactive_service, "invoke_structured", judge)
    monkeypatch.setattr(
        proactive_service,
        "get_provider_settings",
        lambda: SimpleNamespace(event_reminder_llm_match=True, proactive_expiry_minutes=60),
    )

    run(proactive_service.maybe_event_reminders(_event(now)))
    run(proactive_service.maybe_event_reminders(_event(now)))
    assert len(messages.documents) == 1
    assert decisions == [True]
    assert completed == []

    run(proactive_service.maybe_event_reminders(_event(now + dt.timedelta(days=1))))
    assert len(messages.documents) == 2
    assert decisions == []

    messages.documents.clear()

    async def negative_judge(**kwargs):
        return proactive_service.EventReminderMatch(matches=False, reason="not leaving")

    monkeypatch.setattr(proactive_service, "invoke_structured", negative_judge)
    run(proactive_service.maybe_event_reminders(_event(now)))
    assert messages.documents == []

    async def failing_judge(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(proactive_service, "invoke_structured", failing_judge)
    run(proactive_service.maybe_event_reminders(_event(now)))
    assert len(messages.documents) == 1

    messages.documents.clear()
    monkeypatch.setattr(
        proactive_service,
        "get_provider_settings",
        lambda: SimpleNamespace(event_reminder_llm_match=False, proactive_expiry_minutes=60),
    )
    run(proactive_service.maybe_event_reminders(_event(now)))
    assert len(messages.documents) == 1


def test_dated_event_reminder_marks_done(monkeypatch):
    now = dt.datetime(2026, 7, 18, 8, tzinfo=LOCAL_TZ)
    messages = FakeCollection()
    configure_message_store(monkeypatch, messages, now)
    completed = []

    async def matchable(value, *, room_number=None):
        return [_event_reminder("2026-07-18")]

    async def complete(reminder_id, *, mode, now=None):
        completed.append((reminder_id, mode, now))
        return True

    monkeypatch.setattr(proactive_service, "get_matchable_event_reminders", matchable)
    monkeypatch.setattr(proactive_service, "mark_done", complete)
    monkeypatch.setattr(
        proactive_service,
        "get_provider_settings",
        lambda: SimpleNamespace(event_reminder_llm_match=False, proactive_expiry_minutes=60),
    )
    run(proactive_service.maybe_event_reminders(_event(now)))
    assert completed == [("water-1", "delivery", now)]


def test_proactive_indexes(monkeypatch):
    from Blue_dream_agents import db_client

    collection = FakeCollection()
    monkeypatch.setattr(
        db_client, "get_proactive_messages_collection", lambda: collection
    )
    run(db_client.ensure_proactive_indexes())
    assert collection.indexes[0][1]["name"] == "status_1_created_at_1"
    assert collection.indexes[1][1] == {
        "name": "related_id_1",
        "unique": True,
        "partialFilterExpression": {"related_id": {"$type": "string"}},
    }


def test_proactive_endpoint_contracts(client, monkeypatch, api_module):
    checks = []
    appended = []

    async def check(now):
        checks.append(now)

    async def pending(now):
        return [
            {
                "message_id": "pm_1",
                "trigger_type": "reminder",
                "text": "Take your medicine.",
                "image_path": "/storage/highlighted/legacy-stove.jpg",
                "action": None,
                "created_at": now.isoformat(),
                "related_id": "reminder-1:2026-07-18T09:00:00-07:00",
                "status": "delivered",
            }
        ]

    async def append(session_id, role, text):
        appended.append((session_id, role, text))
        return True

    async def acknowledge(message_id):
        return message_id == "pm_1"

    monkeypatch.setattr(api_module, "check_due_reminders", check)
    monkeypatch.setattr(api_module, "get_pending_proactive", pending)
    monkeypatch.setattr(api_module, "append_conversation_turn", append)
    monkeypatch.setattr(api_module, "acknowledge_proactive", acknowledge)

    response = client.get("/proactive/pending?session_id=browser-1")
    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "message_id": "pm_1",
            "trigger_type": "reminder",
            "text": "Take your medicine.",
            "image_path": "/storage/highlighted/legacy-stove.jpg",
            "action": None,
            "created_at": checks[0].isoformat(),
            "related_id": "reminder-1:2026-07-18T09:00:00-07:00",
        }
    ]
    assert appended == [("browser-1", "assistant", "Take your medicine.")]
    assert client.post("/proactive/pm_1/ack").json() == {"ok": True}
    assert client.post("/proactive/missing/ack").status_code == 404
