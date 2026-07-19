import asyncio
import copy
from types import SimpleNamespace

from pymongo.errors import DuplicateKeyError

from Blue_dream_agents import proactive_service, web_push


class FakeMessages:
    def __init__(self):
        self.documents = []
        self.raise_duplicate = False
        self.hide_first_find = False
        self.find_calls = 0

    async def find_one(self, query):
        self.find_calls += 1
        if self.hide_first_find and self.find_calls == 1:
            return None
        match = next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ),
            None,
        )
        return copy.deepcopy(match)

    async def insert_one(self, document):
        if self.raise_duplicate:
            raise DuplicateKeyError("duplicate")
        self.documents.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document["message_id"])


def _configure(monkeypatch, collection):
    async def noop_indexes():
        return None

    monkeypatch.setattr(proactive_service, "initialize_proactive_indexes", noop_indexes)
    monkeypatch.setattr(
        proactive_service, "get_proactive_messages_collection", lambda: collection
    )


def test_create_message_pushes_once_but_not_on_dedupe(monkeypatch):
    collection = FakeMessages()
    _configure(monkeypatch, collection)
    pushed = []

    async def record(document):
        pushed.append(copy.deepcopy(document))

    monkeypatch.setattr(
        proactive_service.web_push, "send_for_proactive_message", record
    )

    first = asyncio.run(
        proactive_service.create_message(
            trigger_type="reminder", text="Take your water.", related_id="reminder-1"
        )
    )
    second = asyncio.run(
        proactive_service.create_message(
            trigger_type="reminder", text="Duplicate", related_id="reminder-1"
        )
    )

    assert first == second
    assert len(pushed) == 1
    assert pushed[0]["message_id"] == first


def test_duplicate_key_recovery_does_not_push(monkeypatch):
    collection = FakeMessages()
    collection.documents.append(
        {
            "message_id": "pm_existing",
            "related_id": "same-trigger",
            "status": "pending",
        }
    )
    collection.raise_duplicate = True
    collection.hide_first_find = True
    _configure(monkeypatch, collection)
    pushed = []

    async def record(document):
        pushed.append(document)

    monkeypatch.setattr(
        proactive_service.web_push, "send_for_proactive_message", record
    )

    message_id = asyncio.run(
        proactive_service.create_message(
            trigger_type="safety", text="Please step away.", related_id="same-trigger"
        )
    )

    assert message_id == "pm_existing"
    assert pushed == []


def test_push_sender_failure_never_changes_pending_message(monkeypatch):
    collection = FakeMessages()
    _configure(monkeypatch, collection)

    async def fail(document):
        raise RuntimeError("push transport unavailable")

    monkeypatch.setattr(
        proactive_service.web_push, "send_for_proactive_message", fail
    )

    message_id = asyncio.run(
        proactive_service.create_message(
            trigger_type="safety", text="The stove may be hot.", related_id="alert-1"
        )
    )

    assert message_id.startswith("pm_")
    assert collection.documents[0]["status"] == "pending"


def test_unconfigured_push_is_clean_noop(monkeypatch):
    monkeypatch.setattr(web_push, "_config", lambda: ("", "", "mailto:test@example.com"))
    monkeypatch.setattr(web_push, "_not_configured_logged", False)

    result = asyncio.run(web_push.send_to_patient_subscriptions({"title": "Test"}))

    assert result == {"status": "not_configured", "sent": 0, "failed": 0}
