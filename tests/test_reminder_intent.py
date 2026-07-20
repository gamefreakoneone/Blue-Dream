import asyncio
import datetime as dt

from Blue_dream_agents import jeeves
from Blue_dream_agents.jeeves import JeevesResponse, QueryRoute
from Blue_dream_agents.reminder_service import EventTrigger, ReminderExtraction
from Blue_dream_agents.timezone_utils import LOCAL_TZ


def run(coro):
    return asyncio.run(coro)


def test_reminder_route_creates_chat_reminder_with_session(monkeypatch):
    now = dt.datetime(2026, 7, 20, 14, 0, tzinfo=LOCAL_TZ)
    due = now.replace(hour=21)
    captured = {}

    async def resolve(query, conversation_context):
        return query, None

    async def route(query):
        return QueryRoute(intent="reminder", reason="explicit request")

    async def structured(**kwargs):
        assert kwargs["output_model"] is ReminderExtraction
        assert kwargs["prompt"]["timezone"] == "America/Los_Angeles"
        return ReminderExtraction(
            is_reminder=True,
            text="take my pills",
            trigger_type="time",
            due_at=due,
        )

    async def create(reminder, **kwargs):
        captured["reminder"] = reminder
        captured["kwargs"] = kwargs
        return {
            "reminder_id": "reminder-1",
            "text": reminder.text,
            "due_at": due.isoformat(),
            "source": kwargs["source"],
            "origin_context": kwargs["origin_context"],
        }

    monkeypatch.setattr(jeeves, "_resolve_query_with_context", resolve)
    monkeypatch.setattr(jeeves, "_route_query", route)
    monkeypatch.setattr(jeeves, "invoke_structured", structured)
    monkeypatch.setattr(jeeves, "create_reminder", create)
    monkeypatch.setattr(jeeves, "now_local", lambda: now)

    response = run(
        jeeves.run_single_query(
            "Remind me to take my pills at 9pm",
            session_id="session-1",
        )
    )

    assert response.response_type == "general"
    assert response.text == (
        "Of course. I'll remind you to take my pills today at 9:00 PM."
    )
    assert response.data["route_intent"] == "reminder"
    assert response.data["route_reason"] == "explicit request"
    assert response.data["reminder"]["source"] == "chat"
    assert captured["kwargs"] == {
        "source": "chat",
        "origin_context": {
            "session_id": "session-1",
            "created_from_text": "Remind me to take my pills at 9pm",
        },
    }


def test_reminder_extraction_misfire_falls_back_to_general(monkeypatch):
    created = []

    async def structured(**kwargs):
        return ReminderExtraction(is_reminder=False)

    async def create(*args, **kwargs):
        created.append((args, kwargs))

    async def general(query, conversation_context=None):
        assert conversation_context == "Earlier context"
        return JeevesResponse(response_type="general", text="A normal answer")

    monkeypatch.setattr(jeeves, "invoke_structured", structured)
    monkeypatch.setattr(jeeves, "create_reminder", create)
    monkeypatch.setattr(jeeves, "_handle_general_query", general)

    response = run(
        jeeves._handle_reminder_query(
            "Did I take my medicine today?",
            session_id="session-1",
            conversation_context="Earlier context",
        )
    )

    assert response.text == "A normal answer"
    assert response.data == {
        "route_intent": "reminder",
        "reminder_fallback": True,
    }
    assert created == []


def test_reminder_creation_failure_returns_fixed_patient_safe_text(monkeypatch):
    now = dt.datetime(2026, 7, 20, 14, 0, tzinfo=LOCAL_TZ)

    async def structured(**kwargs):
        return ReminderExtraction(
            is_reminder=True,
            text="take my pills",
            trigger_type="time",
            due_at=now.replace(hour=21),
        )

    async def fail_create(*args, **kwargs):
        raise RuntimeError("SENTINEL_REMINDER_SECRET")

    monkeypatch.setattr(jeeves, "invoke_structured", structured)
    monkeypatch.setattr(jeeves, "create_reminder", fail_create)
    monkeypatch.setattr(jeeves, "now_local", lambda: now)

    response = run(jeeves._handle_reminder_query("Remind me at 9pm"))

    assert response.text == (
        "I had a little trouble saving that reminder just now. "
        "Could you ask me again in a moment?"
    )
    assert "SENTINEL" not in response.text
    assert response.data["reminder_failed"] is True


def test_event_reminder_without_time_constraint_uses_full_day_window(monkeypatch):
    now = dt.datetime(2026, 7, 20, 14, 0, tzinfo=LOCAL_TZ)
    captured = {}

    async def structured(**kwargs):
        assert kwargs["prompt"]["user_message"] == (
            "when I leave the bedroom, remind me to pick up my bag"
        )
        assert "full-day window 00:00 through 23:59" in kwargs["system_prompt"]
        return ReminderExtraction(
            is_reminder=True,
            text="pick up my bag",
            trigger_type="event",
            event_trigger=EventTrigger(
                room_number=0,
                window_start="00:00",
                window_end="23:59",
                condition="leaving the bedroom",
            ),
        )

    async def create(reminder, **kwargs):
        captured["reminder"] = reminder
        return {
            "reminder_id": "event-reminder-1",
            **reminder.model_dump(mode="json"),
            "source": kwargs["source"],
            "origin_context": kwargs["origin_context"],
        }

    monkeypatch.setattr(jeeves, "invoke_structured", structured)
    monkeypatch.setattr(jeeves, "create_reminder", create)
    monkeypatch.setattr(jeeves, "now_local", lambda: now)

    response = run(
        jeeves._handle_reminder_query(
            "when I leave the bedroom, remind me to pick up my bag",
            session_id="session-event",
        )
    )

    trigger = captured["reminder"].event_trigger
    assert trigger.window_start == "00:00"
    assert trigger.window_end == "23:59"
    assert response.data["reminder"]["event_trigger"] == {
        "room_number": 0,
        "window_start": "00:00",
        "window_end": "23:59",
        "condition": "leaving the bedroom",
        "valid_date": None,
    }


def test_confirmation_text_time_daily_and_event():
    now = dt.datetime(2026, 7, 20, 14, 0, tzinfo=LOCAL_TZ)
    daily = ReminderExtraction(
        is_reminder=True,
        text="drink water",
        trigger_type="time",
        due_at=dt.datetime(2026, 7, 21, 8, 5, tzinfo=LOCAL_TZ),
        recurrence="daily",
    )
    event = ReminderExtraction(
        is_reminder=True,
        text="take my water bottle",
        trigger_type="event",
        event_trigger=EventTrigger(
            window_start="06:00",
            window_end="11:00",
            condition="leaving for a walk",
        ),
    )

    assert jeeves._confirmation_text(daily, now=now) == (
        "Of course. I'll remind you to drink water tomorrow at 8:05 AM. "
        "I'll repeat it every day."
    )
    assert jeeves._confirmation_text(event, now=now) == (
        "Of course. I'll remind you to take my water bottle when I notice "
        "leaving for a walk."
    )


def test_router_prompt_excludes_past_event_questions_from_reminder(monkeypatch):
    captured = {}

    async def structured(**kwargs):
        captured.update(kwargs)
        return QueryRoute(intent="time", reason="asks whether it happened")

    monkeypatch.setattr(jeeves, "invoke_structured", structured)
    route = run(jeeves._route_query("Did I take my medicine today?"))

    assert route.intent == "time"
    assert "Questions about whether something already happened are never 'reminder'." in (
        captured["structured_output_prompt"]
    )
    assert "Choose 'reminder' only" in captured["system_prompt"]
