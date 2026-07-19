"""Seed and verify spec 0008 against an isolated live Mongo/API stack."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Blue_dream_agents.alert_service import create_alert_for_safety_assessment
from Blue_dream_agents.db_client import (
    close_mongo_client,
    ensure_alert_indexes,
    ensure_conversation_indexes,
    ensure_events_indexes,
    ensure_memory_lifecycle_indexes,
    ensure_profile_indexes,
    ensure_proactive_indexes,
    ensure_reminder_indexes,
    get_mongo_client,
)
from Blue_dream_agents.llm.client import close_llm_clients
from Blue_dream_agents.memory_schema import MemoryEvent, memory_event_to_mongo
from Blue_dream_agents.proactive_service import (
    create_message,
    maybe_event_reminders,
    maybe_morning_report,
)
from Blue_dream_agents.reminder_service import EventTrigger, ReminderCreate, create_reminder
from Blue_dream_agents.safety_agent import SafetyAssessment
from Blue_dream_agents.timezone_utils import LOCAL_TZ, now_local, to_local


FALL_SCREENSHOT = "Storage/screenshots/camera_0/fall_alert_0_2026-07-18_00-54-42-211029.jpg"
EVENT_TEXT = "Please remember your water bottle before your walk."
TIME_TEXT = "Please take your morning medicine."
SAFETY_TEXT = "Please sit down somewhere safe and call for help if you feel hurt."
UI_TEXT = "Please return to the kitchen and check that everything is safe."


def assert_safe_environment() -> None:
    errors: list[str] = []
    if os.environ.get("SPEC0008_REHEARSAL_ALLOW_DESTRUCTIVE") != "1":
        errors.append("SPEC0008_REHEARSAL_ALLOW_DESTRUCTIVE must equal 1")
    uri = os.environ.get("MONGODB_URI", "").strip()
    try:
        parsed = urlparse(uri)
        port = parsed.port
    except ValueError:
        parsed = None
        port = None
    if parsed is None or parsed.scheme != "mongodb" or not parsed.hostname or port is None:
        errors.append("MONGODB_URI must specify an explicit MongoDB host and port")
    elif port == 27017:
        errors.append("MONGODB_URI must not use the normal port 27017")
    chroma = os.environ.get("CHROMA_PERSIST_DIR", "").strip()
    if not chroma or Path(chroma).resolve() == (ROOT / "Storage" / "chroma").resolve():
        errors.append("CHROMA_PERSIST_DIR must be an isolated path")
    if errors:
        raise RuntimeError("Refusing unsafe spec 0008 rehearsal: " + "; ".join(errors))


def event(event_id: str, timestamp: dt.datetime, semantic_text: str) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id,
        timestamp=timestamp,
        room_number=1,
        room_name="Living Room",
        semantic_text=semantic_text,
        video_description=semantic_text,
    )


async def seed() -> dict:
    database = get_mongo_client().dementia_assistance
    for name in (
        "events",
        "memory_summaries",
        "profile_facts",
        "reminders",
        "safety_alerts",
        "proactive_messages",
        "conversation_sessions",
        "devices",
    ):
        await database[name].delete_many({})

    await asyncio.gather(
        ensure_events_indexes(),
        ensure_alert_indexes(),
        ensure_conversation_indexes(),
        ensure_profile_indexes(),
        ensure_reminder_indexes(),
        ensure_memory_lifecycle_indexes(),
        ensure_proactive_indexes(),
    )

    now = now_local()
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    first_timestamp = dt.datetime.combine(today, dt.time(6, 30), tzinfo=LOCAL_TZ)
    first = event(
        "spec0008-first-event",
        first_timestamp,
        "You started your morning calmly in the living room.",
    )
    await database.events.insert_one(memory_event_to_mongo(first))
    await database.memory_summaries.insert_one(
        {
            "summary_id": f"spec0008-summary-{yesterday.isoformat()}",
            "period": "day",
            "date": yesterday.isoformat(),
            "room_number": 1,
            "room_name": "Living Room",
            "text": "Yesterday you read a book and spoke with Sarah.",
            "source_event_ids": [],
            "created_at": now,
        }
    )
    await database.profile_facts.insert_one(
        {
            "fact_id": "spec0008-safety-fact",
            "category": "safety",
            "text": "Use the handrail when walking downstairs.",
            "confidence": 1.0,
            "pinned": True,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    await maybe_morning_report(first_timestamp)
    await maybe_morning_report(first_timestamp)

    await create_reminder(
        ReminderCreate(
            text=EVENT_TEXT,
            trigger_type="event",
            event_trigger=EventTrigger(
                room_number=1,
                window_start="06:00",
                window_end="11:00",
                condition="you put on your shoes and leave the living room for a walk",
            ),
        ),
        source="api",
    )
    outside = event(
        "spec0008-outside-window",
        dt.datetime.combine(today, dt.time(12, 0), tzinfo=LOCAL_TZ),
        "You put on your shoes and left the living room for a walk.",
    )
    await maybe_event_reminders(outside)
    outside_count = await database.proactive_messages.count_documents(
        {"text": EVENT_TEXT}
    )
    matching = event(
        "spec0008-matching-event",
        dt.datetime.combine(today, dt.time(8, 0), tzinfo=LOCAL_TZ),
        "You put on your shoes and left the living room for a walk.",
    )
    await maybe_event_reminders(matching)
    await maybe_event_reminders(matching)

    await create_reminder(
        ReminderCreate(
            text=TIME_TEXT,
            due_at=now - dt.timedelta(minutes=1),
            recurrence="daily",
        ),
        source="api",
    )

    safety_event = MemoryEvent(
        event_id="spec0008-hazard-event",
        timestamp=now,
        room_number=0,
        room_name="Bedroom",
        semantic_text="A possible fall was detected beside the bed.",
        video_description="A possible fall was detected beside the bed.",
        screenshot_path=FALL_SCREENSHOT,
    )
    await create_alert_for_safety_assessment(
        safety_event,
        SafetyAssessment(
            warning_needed=True,
            severity="high",
            hazard_type="possible_fall",
            confidence=0.95,
            patient_message=SAFETY_TEXT,
            detailed_explanation="A possible fall was detected beside the bed.",
            recommended_action="Sit somewhere safe and call for help if needed.",
        ),
    )

    expired_id = await create_message(
        trigger_type="safety",
        text="This stale warning must never be delivered.",
        related_id="spec0008-expired",
        expires_minutes=1,
    )
    await database.proactive_messages.update_one(
        {"message_id": expired_id},
        {"$set": {"expires_at": now - dt.timedelta(seconds=1)}},
    )
    return {
        "outside_window_message_count": outside_count,
        "morning_message_count": await database.proactive_messages.count_documents(
            {"trigger_type": "morning_report"}
        ),
        "event_message_count": await database.proactive_messages.count_documents(
            {"text": EVENT_TEXT}
        ),
        "safety_message_count": await database.proactive_messages.count_documents(
            {"text": SAFETY_TEXT}
        ),
    }


async def seed_ui() -> dict:
    message_id = await create_message(
        trigger_type="safety",
        text=UI_TEXT,
        image_path=FALL_SCREENSHOT,
        action={"label": "Review safety guidance", "url": "https://example.com/safety"},
        related_id="spec0008-ui-proof",
    )
    return {"ui_message_id": message_id, "ui_text": UI_TEXT}


async def verify() -> dict:
    database = get_mongo_client().dementia_assistance
    acknowledged = await database.proactive_messages.count_documents(
        {"status": "acknowledged"}
    )
    expired = await database.proactive_messages.find_one(
        {"related_id": "spec0008-expired"}
    )
    event_messages = await database.proactive_messages.count_documents(
        {"text": EVENT_TEXT}
    )
    morning_messages = await database.proactive_messages.count_documents(
        {"trigger_type": "morning_report"}
    )
    daily = await database.reminders.find_one({"text": TIME_TEXT})
    event_reminder = await database.reminders.find_one({"text": EVENT_TEXT})
    session = await database.conversation_sessions.find_one(
        {"session_id": "spec0008-browser-a"}
    )
    if acknowledged != 4:
        raise AssertionError(f"Expected four acknowledged trigger messages, got {acknowledged}")
    if expired is None or expired.get("status") != "pending":
        raise AssertionError("Expired pending message was delivered")
    if event_messages != 1 or morning_messages != 1:
        raise AssertionError("Event or morning dedupe failed")
    if (
        daily is None
        or daily.get("status") != "active"
        or to_local(daily["due_at"]) <= now_local()
    ):
        raise AssertionError("Daily reminder did not roll forward")
    if event_reminder is None or event_reminder.get("status") != "active":
        raise AssertionError("Undated event reminder did not remain active")
    turns = list((session or {}).get("turns") or [])
    if len(turns) != 4 or any(turn.get("role") != "assistant" for turn in turns):
        raise AssertionError("Delivered proactive turns were not appended to the session")
    return {
        "acknowledged_messages": acknowledged,
        "expired_remained_pending": True,
        "event_same_day_dedupe": event_messages == 1,
        "morning_first_event_dedupe": morning_messages == 1,
        "daily_rolled_forward_to": daily["due_at"],
        "undated_event_reminder_active": True,
        "conversation_assistant_turns": len(turns),
    }


async def main(mode: str) -> None:
    assert_safe_environment()
    try:
        if mode == "seed":
            result = await seed()
        elif mode == "ui":
            result = await seed_ui()
        else:
            result = await verify()
        print(json.dumps(result, indent=2, default=str))
    finally:
        await close_llm_clients()
        await close_mongo_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "verify", "ui"))
    args = parser.parse_args()
    asyncio.run(main(args.mode))
