import asyncio
import copy
import datetime as dt
from types import SimpleNamespace

from bson import ObjectId

from Blue_dream_agents import conversation_memory, jeeves, profile_memory
from Blue_dream_agents.reminder_service import (
    EventTrigger,
    ReminderCreate,
    ReminderService,
)
from Blue_dream_agents.timezone_utils import LOCAL_TZ


def _get_nested(document, path):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _set_nested(document, path, value):
    target = document
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = copy.deepcopy(value)


def _matches(document, query):
    for key, expected in query.items():
        actual = _get_nested(document, key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
        elif isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field_or_fields, direction=None):
        fields = (
            field_or_fields
            if isinstance(field_or_fields, list)
            else [(field_or_fields, direction)]
        )
        for field, sort_direction in reversed(fields):
            self.documents.sort(
                key=lambda document: (
                    _get_nested(document, field) is None,
                    _get_nested(document, field),
                ),
                reverse=sort_direction == -1,
            )
        return self

    def __aiter__(self):
        self._iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = copy.deepcopy(list(documents or []))
        self.indexes = []

    async def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))
        return kwargs.get("name")

    async def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return copy.deepcopy(document)
        return None

    def find(self, query):
        return FakeCursor(
            [copy.deepcopy(document) for document in self.documents if _matches(document, query)]
        )

    async def insert_one(self, document):
        self.documents.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("_id"))

    async def update_one(self, query, update, upsert=False):
        target = next((doc for doc in self.documents if _matches(doc, query)), None)
        inserted = False
        if target is None and upsert:
            target = {
                key: copy.deepcopy(value)
                for key, value in query.items()
                if not isinstance(value, dict)
            }
            self.documents.append(target)
            inserted = True
        if target is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        if inserted:
            for key, value in update.get("$setOnInsert", {}).items():
                _set_nested(target, key, value)
        for key, value in update.get("$set", {}).items():
            _set_nested(target, key, value)
        for key, value in update.get("$push", {}).items():
            current = _get_nested(target, key)
            if current is None:
                _set_nested(target, key, [])
                current = _get_nested(target, key)
            current.append(copy.deepcopy(value))
        return SimpleNamespace(matched_count=0 if inserted else 1, modified_count=1)


def _run(coro):
    return asyncio.run(coro)


def test_conversation_persists_across_store_instances_and_reset():
    collection = FakeCollection()
    first = conversation_memory.ConversationMemoryStore(collection, max_turns=4)

    assert _run(first.get_context(None)) == ""
    assert _run(first.append_turn(None, "user", "ignored")) is False
    assert collection.documents == []

    _run(first.append_turn("session-1", "user", "My daughter is Sarah."))
    _run(first.append_turn("session-1", "assistant", "I will remember that."))
    assert "Sarah" in _run(first.get_context("session-1"))

    _run(first.append_turn("session-1", "user", "When does she visit?"))
    assert "When does she visit?" in _run(first.get_context("session-1"))

    restarted = conversation_memory.ConversationMemoryStore(collection, max_turns=4)
    assert "Sarah" in _run(restarted.get_context("session-1"))
    assert _run(restarted.reset("session-1")) is True
    assert _run(restarted.get_context("session-1")) == ""
    assert collection.documents[0]["status"] == "closed"


def test_conversation_summary_trims_only_after_success(monkeypatch):
    collection = FakeCollection()
    store = conversation_memory.ConversationMemoryStore(collection, max_turns=2)

    async def summarize(**kwargs):
        return conversation_memory.ConversationSummary(summary="Merged durable summary")

    monkeypatch.setattr(conversation_memory, "invoke_structured", summarize)
    for role, text in (
        ("user", "one"),
        ("assistant", "two"),
        ("user", "three"),
    ):
        _run(store.append_turn("summary", role, text))

    document = collection.documents[0]
    assert document["summary"] == "Merged durable summary"
    assert [turn["text"] for turn in document["turns"]] == ["two", "three"]
    assert _run(store.get_context("summary")).startswith(
        "Earlier in this conversation: Merged durable summary"
    )

    failing_collection = FakeCollection()
    failing = conversation_memory.ConversationMemoryStore(
        failing_collection, max_turns=2
    )

    async def fail(**kwargs):
        raise RuntimeError("summary unavailable")

    monkeypatch.setattr(conversation_memory, "invoke_structured", fail)
    for role, text in (
        ("user", "one"),
        ("assistant", "two"),
        ("user", "three"),
    ):
        _run(failing.append_turn("failure", role, text))
    assert len(failing_collection.documents[0]["turns"]) == 3
    assert failing_collection.documents[0]["summary"] == ""


def test_combined_extraction_stores_fact_and_chat_reminder(monkeypatch):
    collection = FakeCollection()
    reminders = []

    async def record_reminder(reminder, **kwargs):
        reminders.append((reminder, kwargs))
        return {"reminder_id": "r1"}

    responses = iter(
        [
            profile_memory.TurnMemoryExtraction(
                facts=[
                    profile_memory.ExtractedFact(
                        category="person",
                        text="The patient's daughter is Sarah.",
                        confidence=0.95,
                    )
                ],
                reminder={
                    "is_reminder": True,
                    "text": "Take the water bottle",
                    "trigger_type": "event",
                    "recurrence": "none",
                    "event_trigger": {
                        "room_number": 1,
                        "window_start": "06:00",
                        "window_end": "11:00",
                        "condition": "leaving for a walk",
                        "valid_date": "2026-07-19",
                    },
                },
            ),
            profile_memory.FactDedupDecision(action="add"),
        ]
    )

    async def structured(**kwargs):
        return next(responses)

    monkeypatch.setattr(profile_memory, "invoke_structured", structured)
    service = profile_memory.ProfileMemoryService(
        collection, reminder_creator=record_reminder
    )
    _run(
        service.extract_and_store(
            "When I leave tomorrow, remind me to take my water bottle. My daughter is Sarah.",
            "Of course.",
            session_id="session-a",
        )
    )

    assert collection.documents[0]["text"].endswith("Sarah.")
    reminder, metadata = reminders[0]
    assert reminder.trigger_type == "event"
    assert reminder.event_trigger.room_number == 1
    assert metadata["source"] == "chat"
    assert metadata["origin_context"]["session_id"] == "session-a"


def test_exact_repeated_turn_is_idempotent_across_category_drift(monkeypatch):
    collection = FakeCollection()
    first = profile_memory.TurnMemoryExtraction(
        facts=[
            profile_memory.ExtractedFact(
                category="person", text="Daughter Sarah visits Sundays", confidence=0.9
            )
        ]
    )
    repeated_with_drift = profile_memory.TurnMemoryExtraction(
        facts=[
            profile_memory.ExtractedFact(
                category="routine", text="Sarah visits every Sunday", confidence=0.9
            )
        ]
    )
    responses = iter(
        [
            first,
            profile_memory.FactDedupDecision(action="add"),
            repeated_with_drift,
        ]
    )

    async def structured(**kwargs):
        return next(responses)

    monkeypatch.setattr(profile_memory, "invoke_structured", structured)
    service = profile_memory.ProfileMemoryService(collection)
    statement = "My daughter Sarah visits me on Sundays."
    _run(service.extract_and_store(statement, "Thanks."))
    _run(service.extract_and_store(statement, "I remember."))
    assert len(collection.documents) == 1


def test_fact_dedup_update_skip_add_and_cap(monkeypatch):
    now = dt.datetime(2026, 7, 18, 9, tzinfo=LOCAL_TZ)
    existing = [
        {
            "_id": ObjectId(),
            "fact_id": "pinned",
            "category": "preference",
            "text": "Likes tea",
            "confidence": 0.9,
            "pinned": True,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        {
            "_id": ObjectId(),
            "fact_id": "low",
            "category": "routine",
            "text": "Walks sometimes",
            "confidence": 0.2,
            "pinned": False,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    ]
    collection = FakeCollection(existing)
    service = profile_memory.ProfileMemoryService(collection, max_active_facts=2)
    decisions = iter(
        [
            profile_memory.FactDedupDecision(
                action="update", target_fact_id="pinned", merged_text="Likes green tea"
            ),
            profile_memory.FactDedupDecision(action="skip"),
            profile_memory.FactDedupDecision(action="add"),
        ]
    )

    async def structured(**kwargs):
        return next(decisions)

    monkeypatch.setattr(profile_memory, "invoke_structured", structured)
    assert _run(
        service._deduplicate_and_store(
            profile_memory.ExtractedFact(
                category="preference", text="Likes green tea", confidence=0.8
            )
        )
    ) == "update"
    assert _run(
        service._deduplicate_and_store(
            profile_memory.ExtractedFact(
                category="routine", text="Walks sometimes", confidence=0.8
            )
        )
    ) == "skip"
    assert _run(
        service._deduplicate_and_store(
            profile_memory.ExtractedFact(
                category="person", text="Daughter is Sarah", confidence=0.8
            )
        )
    ) == "add"
    _run(service._enforce_cap())

    pinned = next(doc for doc in collection.documents if doc["fact_id"] == "pinned")
    low = next(doc for doc in collection.documents if doc["fact_id"] == "low")
    assert pinned["text"] == "Likes green tea"
    assert pinned["status"] == "active"
    assert low["status"] == "archived"
    assert _run(service.get_active_facts())[0]["fact_id"] == "pinned"
    assert "[pinned]" in _run(service.render_profile_block())


def test_profile_pin_and_archive():
    now = dt.datetime(2026, 7, 18, 9, tzinfo=LOCAL_TZ)
    collection = FakeCollection(
        [
            {
                "fact_id": "fact-1",
                "category": "person",
                "text": "Daughter is Sarah",
                "confidence": 0.9,
                "pinned": False,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    service = profile_memory.ProfileMemoryService(collection)
    assert _run(service.pin("fact-1")) is True
    assert collection.documents[0]["pinned"] is True
    assert _run(service.archive("fact-1")) is True
    assert collection.documents[0]["status"] == "archived"
    assert collection.documents[0]["pinned"] is False
    assert _run(service.pin("missing")) is False


def test_general_prompt_includes_profile_block(monkeypatch):
    captured = {}

    async def profile_block():
        return "What you know about the patient:\n- (person) Daughter is Sarah"

    async def text(**kwargs):
        captured.update(kwargs)
        return "Sarah is visiting."

    monkeypatch.setattr(jeeves, "render_profile_block", profile_block)
    monkeypatch.setattr(jeeves, "invoke_text", text)
    response = _run(jeeves._handle_general_query("Who is visiting?"))
    assert response.text == "Sarah is visiting."
    assert "Daughter is Sarah" in captured["system_prompt"]
    assert "fixed home CCTV" in captured["system_prompt"]


def test_insufficient_semantic_evidence_can_fall_back_to_profile(monkeypatch):
    from Blue_dream_agents.semantic_search import SemanticSearchResult

    async def retrieval(query):
        return SemanticSearchResult(
            success=False,
            text="No monitoring evidence",
            query=query,
            match_count=0,
            top_k=5,
            matches=[],
        )

    async def judge(query, result):
        return jeeves.SemanticDecision(decision="insufficient_evidence")

    async def block():
        return "What you know about the patient:\n- (person) Daughter is Sarah"

    async def synthesize(query, result, **kwargs):
        return "Your daughter's name is Sarah."

    monkeypatch.setattr(jeeves, "run_semantic_retrieval", retrieval)
    monkeypatch.setattr(jeeves, "_judge_semantic_retrieval", judge)
    monkeypatch.setattr(jeeves, "render_profile_block", block)
    monkeypatch.setattr(jeeves, "_synthesize_semantic_answer", synthesize)

    response = _run(jeeves._handle_semantic_query("What is my daughter's name?"))
    assert response.text == "Your daughter's name is Sarah."
    assert response.data["profile_fallback_used"] is True


def test_reminder_round_trip_due_boundary_and_daily_rollover():
    collection = FakeCollection()
    service = ReminderService(collection)
    due = dt.datetime(2026, 7, 18, 8, tzinfo=LOCAL_TZ)
    created = _run(
        service.create(
            ReminderCreate(
                text="Take pill",
                due_at=due,
                recurrence="daily",
            )
        )
    )
    assert created["trigger_type"] == "time"
    assert created["event_trigger"] is None
    assert len(_run(service.get_due(due))) == 1
    assert _run(service.get_due(due - dt.timedelta(seconds=1))) == []

    assert _run(service.mark_done(created["reminder_id"], now=due)) is True
    stored = collection.documents[0]
    assert stored["status"] == "active"
    assert stored["due_at"] == due + dt.timedelta(days=1)

    event = _run(
        service.create(
            ReminderCreate(
                text="Take water bottle",
                trigger_type="event",
                event_trigger=EventTrigger(
                    room_number=1,
                    window_start="06:00",
                    window_end="11:00",
                    condition="leaving for a walk",
                    valid_date=dt.date(2026, 7, 19),
                ),
            )
        )
    )
    assert event["event_trigger"]["valid_date"] == "2026-07-19"
    assert event["event_trigger"]["room_number"] == 1
    assert _run(service.mark_done(event["reminder_id"])) is True


def test_matchable_event_reminder_date_window_and_overnight():
    today = dt.date(2026, 7, 18)
    collection = FakeCollection()
    service = ReminderService(collection)

    def add(text, start, end, valid_date, room):
        return _run(
            service.create(
                ReminderCreate(
                    text=text,
                    trigger_type="event",
                    event_trigger=EventTrigger(
                        room_number=room,
                        window_start=start,
                        window_end=end,
                        condition="leaving home",
                        valid_date=valid_date,
                    ),
                )
            )
        )

    add("today", "06:00", "11:00", today, 1)
    add("daily", "06:00", "11:00", None, None)
    add("other date", "06:00", "11:00", today + dt.timedelta(days=1), 2)
    add("outside", "12:00", "13:00", today, 3)
    add("overnight", "22:00", "02:00", today, 4)

    morning = _run(
        service.get_matchable_events(
            dt.datetime(2026, 7, 18, 6, 0, tzinfo=LOCAL_TZ)
        )
    )
    assert {item["text"] for item in morning} == {"today", "daily"}
    assert {item["event_trigger"]["room_number"] for item in morning} == {1, None}

    overnight = _run(
        service.get_matchable_events(
            dt.datetime(2026, 7, 18, 23, 30, tzinfo=LOCAL_TZ)
        )
    )
    assert [item["text"] for item in overnight] == ["overnight"]


def test_memory_indexes(monkeypatch):
    from Blue_dream_agents import db_client

    conversations = FakeCollection()
    facts = FakeCollection()
    reminders = FakeCollection()
    monkeypatch.setattr(
        db_client, "get_conversation_sessions_collection", lambda: conversations
    )
    monkeypatch.setattr(db_client, "get_profile_facts_collection", lambda: facts)
    monkeypatch.setattr(db_client, "get_reminders_collection", lambda: reminders)

    _run(db_client.ensure_conversation_indexes())
    _run(db_client.ensure_profile_indexes())
    _run(db_client.ensure_reminder_indexes())
    assert conversations.indexes[0][1] == {"name": "session_id_1", "unique": True}
    assert facts.indexes[0][1]["name"] == "status_1_category_1"
    assert {index[1]["name"] for index in reminders.indexes} == {
        "status_1_due_at_1",
        "status_1_trigger_type_1",
    }


def test_new_endpoint_contracts(client, monkeypatch, api_module):
    now = "2026-07-18T09:00:00-07:00"

    async def facts():
        return [
            {
                "fact_id": "fact-1",
                "category": "person",
                "text": "Daughter is Sarah",
                "confidence": 0.9,
                "pinned": True,
                "status": "active",
                "created_at": now,
            }
        ]

    async def true_for_known(identifier):
        return identifier in {"fact-1", "reminder-1"}

    async def reminders():
        return [
            {
                "reminder_id": "reminder-1",
                "text": "Take water bottle",
                "trigger_type": "event",
                "due_at": None,
                "recurrence": "none",
                "event_trigger": {
                    "room_number": 1,
                    "window_start": "06:00",
                    "window_end": "11:00",
                    "condition": "leaving for a walk",
                    "valid_date": "2026-07-19",
                },
                "status": "active",
                "created_at": now,
                "source": "api",
                "origin_context": None,
            }
        ]

    async def create(request, **kwargs):
        payload = request.model_dump(mode="json")
        payload.update(
            {
                "reminder_id": "created",
                "status": "active",
                "created_at": now,
                "source": kwargs["source"],
                "origin_context": kwargs["origin_context"],
            }
        )
        return payload

    monkeypatch.setattr(api_module, "get_active_facts", facts)
    monkeypatch.setattr(api_module, "pin_fact", true_for_known)
    monkeypatch.setattr(api_module, "archive_fact", true_for_known)
    monkeypatch.setattr(api_module, "list_active_reminders", reminders)
    monkeypatch.setattr(api_module, "create_reminder", create)
    monkeypatch.setattr(api_module, "mark_done", true_for_known)

    assert client.get("/memory/profile").json()["facts"][0]["fact_id"] == "fact-1"
    assert client.post("/memory/profile/fact-1/pin").json() == {"ok": True}
    assert client.post("/memory/profile/fact-1/archive").json() == {"ok": True}
    assert client.post("/memory/profile/missing/pin").status_code == 404

    listed = client.get("/reminders").json()["reminders"][0]
    assert listed["event_trigger"]["valid_date"] == "2026-07-19"
    created = client.post(
        "/reminders",
        json={"text": "Take pill", "due_at": now},
    )
    assert created.status_code == 200
    assert created.json()["trigger_type"] == "time"
    assert client.post("/reminders/reminder-1/done").json() == {"ok": True}
    assert client.post("/reminders/missing/done").status_code == 404

    invalid = client.post(
        "/reminders",
        json={"text": "Take bottle", "trigger_type": "event"},
    )
    assert invalid.status_code == 422


def test_extraction_failure_isolated_from_query(client, monkeypatch, api_module):
    async def fail(*args, **kwargs):
        raise RuntimeError("SENTINEL_EXTRACTION_SECRET")

    monkeypatch.setattr(api_module, "extract_and_store", fail)
    response = client.post(
        "/query", json={"query": "My daughter is Sarah", "session_id": "s1"}
    )
    assert response.status_code == 200
    assert response.json()["text"] == "Remembered: My daughter is Sarah"
    assert "SENTINEL_EXTRACTION_SECRET" not in response.text
