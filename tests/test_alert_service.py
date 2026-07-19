import asyncio
import threading

from Blue_dream_agents import alert_service
from Blue_dream_agents.memory_schema import MemoryEvent
from Blue_dream_agents.safety_agent import SafetyAssessment
from Blue_dream_agents.timezone_utils import now_local


class FakeInsertResult:
    inserted_id = "inserted"


class FakeUpdateResult:
    modified_count = 1


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *args):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __aiter__(self):
        self._iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeAlertCollection:
    def __init__(self, documents=None, events=None):
        self.documents = list(documents or [])
        self.events = events if events is not None else []
        self.last_query = None
        self.updates = []

    async def insert_one(self, document):
        self.events.append("insert")
        self.documents.append(document.copy())
        return FakeInsertResult()

    async def update_one(self, query, update):
        self.events.append("update")
        self.updates.append((query, update))
        return FakeUpdateResult()

    def find(self, query):
        self.last_query = query
        matching = [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(matching)


def test_fall_alert_persists_before_caretaker_delivery(monkeypatch):
    events = []
    collection = FakeAlertCollection(events=events)

    async def noop_indexes():
        return None

    async def not_configured(alert):
        events.append("deliver")
        return {"status": "not_configured", "missing": ["recipient"]}

    monkeypatch.setattr(alert_service, "initialize_alert_indexes", noop_indexes)
    monkeypatch.setattr(
        alert_service, "get_safety_alerts_collection", lambda: collection
    )
    monkeypatch.setattr(alert_service, "deliver_caretaker_alert", not_configured)

    result = asyncio.run(
        alert_service.create_alert(
            alert_type="fall",
            severity="high",
            target_role="caretaker",
            title="Possible fall detected",
            body="A possible fall was detected in the Bedroom.",
            room_number=0,
            room_name="Bedroom",
            screenshot_path="Storage/screenshots/fall.jpg",
        )
    )

    inserted = collection.documents[0]
    assert events == ["insert", "deliver", "update"]
    assert inserted["alert_type"] == "fall"
    assert inserted["target_role"] == "caretaker"
    assert inserted["image_path"] == "Storage/screenshots/fall.jpg"
    assert result["delivery_status"] == "not_configured"
    assert result["image_path"] == "/storage/screenshots/fall.jpg"


def test_patient_alert_survives_proactive_trigger_failure(monkeypatch):
    events = []
    collection = FakeAlertCollection(events=events)

    async def noop_indexes():
        return None

    async def fail_proactive(**kwargs):
        events.append("proactive")
        raise RuntimeError("proactive unavailable")

    async def deliver(alert):
        events.append("deliver")
        return {"status": "not_configured"}

    monkeypatch.setattr(alert_service, "initialize_alert_indexes", noop_indexes)
    monkeypatch.setattr(
        alert_service, "get_safety_alerts_collection", lambda: collection
    )
    monkeypatch.setattr(alert_service, "create_proactive_message", fail_proactive)
    monkeypatch.setattr(alert_service, "deliver_patient_alert", deliver)

    result = asyncio.run(
        alert_service.create_alert(
            alert_type="hazard",
            severity="high",
            target_role="patient",
            title="Kitchen warning",
            body="Please return to the kitchen.",
            room_number=1,
            room_name="Living Room",
            screenshot_path="Storage/highlighted/stove.jpg",
        )
    )

    assert events == ["insert", "proactive", "deliver", "update"]
    assert collection.documents[0]["body"] == "Please return to the kitchen."
    assert result["delivery_status"] == "not_configured"


def test_safety_assessment_creates_proactive_warning_with_image(monkeypatch):
    collection = FakeAlertCollection()
    proactive_calls = []

    async def noop_indexes():
        return None

    async def proactive(**kwargs):
        proactive_calls.append(kwargs)
        return "pm_safety"

    async def deliver(alert):
        return {"status": "not_configured"}

    monkeypatch.setattr(alert_service, "initialize_alert_indexes", noop_indexes)
    monkeypatch.setattr(
        alert_service, "get_safety_alerts_collection", lambda: collection
    )
    monkeypatch.setattr(alert_service, "create_proactive_message", proactive)
    monkeypatch.setattr(alert_service, "deliver_patient_alert", deliver)

    event = MemoryEvent(
        event_id="event-hazard",
        timestamp=now_local(),
        room_number=1,
        room_name="Living Room",
        semantic_text="The stove was left on.",
        screenshot_path="Storage/screenshots/stove.jpg",
    )
    assessment = SafetyAssessment(
        warning_needed=True,
        severity="high",
        hazard_type="stove_on",
        confidence=0.95,
        patient_message="Please return to the kitchen and turn off the stove.",
    )

    async def build_alert(event, assessment):
        return {
            "alert_id": "alert-hazard",
            "event_id": event.event_id,
            "target_role": "patient",
            "severity": assessment.severity,
            "body": assessment.patient_message,
            "image_path": "Storage/highlighted/stove.jpg",
            "status": "open",
        }

    monkeypatch.setattr(alert_service, "build_alert_document", build_alert)
    asyncio.run(alert_service.create_alert_for_safety_assessment(event, assessment))

    assert proactive_calls == [
        {
            "trigger_type": "safety",
            "text": "Please return to the kitchen and turn off the stove.",
            "image_path": "Storage/highlighted/stove.jpg",
            "related_id": "alert-hazard",
        }
    ]


def test_caretaker_email_runs_off_event_loop_thread(monkeypatch):
    from Blue_dream_agents.Tools import dementia_email

    monkeypatch.setenv("FALL_ALERT_RECIPIENT_EMAIL", "caretaker@example.test")
    monkeypatch.setattr(alert_service, "get_provider_settings", lambda: object())
    monkeypatch.setattr(alert_service, "_gmail_credentials_available", lambda: True)
    calling_thread = threading.get_ident()
    sent = {}

    class FakeGmailAgent:
        def send_alert_email(self, **kwargs):
            sent.update(kwargs)
            sent["thread_id"] = threading.get_ident()
            return {"success": True, "message_id": "message-1"}

    monkeypatch.setattr(dementia_email, "GmailAgent", FakeGmailAgent)
    result = asyncio.run(
        alert_service.deliver_caretaker_alert(
            {
                "alert_id": "alert-1",
                "title": "Possible fall detected",
                "room_name": "Bedroom",
                "image_path": "",
                "created_at": alert_service.now_local(),
            }
        )
    )

    assert result == {
        "status": "sent",
        "channel": "gmail",
        "message_id": "message-1",
    }
    assert sent["to"] == "caretaker@example.test"
    assert sent["thread_id"] != calling_thread


def test_caretaker_delivery_reports_missing_configuration(monkeypatch):
    monkeypatch.delenv("FALL_ALERT_RECIPIENT_EMAIL", raising=False)
    monkeypatch.setattr(alert_service, "get_provider_settings", lambda: object())
    monkeypatch.setattr(alert_service, "_gmail_credentials_available", lambda: False)

    result = asyncio.run(
        alert_service.deliver_caretaker_alert(
            {"alert_id": "alert-1", "title": "Fall", "created_at": None}
        )
    )

    assert result["status"] == "not_configured"
    assert set(result["missing"]) == {"recipient", "gmail_credentials"}


def test_patient_alert_list_explicitly_filters_target_role(monkeypatch):
    collection = FakeAlertCollection(
        documents=[
            {
                "alert_id": "patient",
                "target_role": "patient",
                "status": "open",
            },
            {
                "alert_id": "caretaker",
                "target_role": "caretaker",
                "status": "open",
            },
        ]
    )

    async def noop_indexes():
        return None

    monkeypatch.setattr(alert_service, "initialize_alert_indexes", noop_indexes)
    monkeypatch.setattr(
        alert_service, "get_safety_alerts_collection", lambda: collection
    )

    results = asyncio.run(alert_service.list_patient_alerts())

    assert collection.last_query == {"target_role": "patient", "status": "open"}
    assert [alert["alert_id"] for alert in results] == ["patient"]
