from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from typing import Any, Literal, Optional
from uuid import uuid4

from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .db_client import (
    ensure_proactive_indexes as ensure_proactive_indexes_in_db,
    get_events_collection,
    get_memory_summaries_collection,
    get_proactive_messages_collection,
)
from .llm.client import invoke_structured
from .llm.prompt_context import with_patient_answer_context
from .llm.settings import get_provider_settings
from .media_paths import to_url_path
from .profile_memory import get_active_facts
from .reminder_service import (
    get_due_reminders,
    get_matchable_event_reminders,
    list_active as list_active_reminders,
    mark_done,
)
from .timezone_utils import LOCAL_TZ, now_local, to_local


logger = logging.getLogger(__name__)
TriggerType = Literal["safety", "morning_report", "reminder"]

_indexes_ready = False
_indexes_lock = asyncio.Lock()


class MorningReportText(BaseModel):
    text: str = Field(min_length=1)


class EventReminderMatch(BaseModel):
    matches: bool
    reason: str = ""


async def initialize_proactive_indexes() -> None:
    """Create proactive indexes once per process, retrying after failures."""

    global _indexes_ready
    if _indexes_ready:
        return
    async with _indexes_lock:
        if _indexes_ready:
            return
        await ensure_proactive_indexes_in_db()
        _indexes_ready = True


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dt.datetime):
        return to_local(value).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def serialize_message(document: dict[str, Any]) -> dict[str, Any]:
    serialized = _json_safe(document)
    serialized.pop("_id", None)
    return serialized


def _expiry_minutes(value: Optional[int]) -> int:
    if value is not None:
        return max(1, int(value))
    return get_provider_settings().proactive_expiry_minutes


async def _message_for_related_id(related_id: str) -> Optional[dict[str, Any]]:
    return await get_proactive_messages_collection().find_one(
        {"related_id": related_id}
    )


async def create_message(
    *,
    trigger_type: TriggerType,
    text: str,
    image_path: Optional[str] = None,
    action: Optional[dict[str, str]] = None,
    related_id: Optional[str] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Persist an agent-initiated message and return its stable message ID."""

    cleaned_text = " ".join(text.split())
    if not cleaned_text:
        raise ValueError("proactive message text is required")
    await initialize_proactive_indexes()

    if related_id:
        existing = await _message_for_related_id(related_id)
        if existing:
            return str(existing["message_id"])

    created_at = now_local()
    message_id = f"pm_{uuid4().hex[:12]}"
    document: dict[str, Any] = {
        "message_id": message_id,
        "trigger_type": trigger_type,
        "text": cleaned_text,
        "image_path": to_url_path(image_path) if image_path else None,
        "action": dict(action) if action else None,
        "status": "pending",
        "created_at": created_at,
        "delivered_at": None,
        "expires_at": created_at
        + dt.timedelta(minutes=_expiry_minutes(expires_minutes)),
    }
    if related_id:
        document["related_id"] = related_id

    try:
        await get_proactive_messages_collection().insert_one(document)
    except DuplicateKeyError:
        if not related_id:
            raise
        existing = await _message_for_related_id(related_id)
        if existing is None:
            raise
        return str(existing["message_id"])
    return message_id


async def get_pending(now: dt.datetime) -> list[dict[str, Any]]:
    """Atomically claim every pending unexpired message, oldest first."""

    await initialize_proactive_indexes()
    local_now = to_local(now)
    messages: list[dict[str, Any]] = []
    collection = get_proactive_messages_collection()
    while True:
        document = await collection.find_one_and_update(
            {"status": "pending", "expires_at": {"$gt": local_now}},
            {
                "$set": {
                    "status": "delivered",
                    "delivered_at": local_now,
                }
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            break
        messages.append(serialize_message(document))
    return messages


async def acknowledge(message_id: str) -> bool:
    """Idempotently acknowledge an existing proactive message."""

    await initialize_proactive_indexes()
    result = await get_proactive_messages_collection().update_one(
        {"message_id": message_id},
        {"$set": {"status": "acknowledged"}},
    )
    return bool(result.matched_count)


async def check_due_reminders(now: dt.datetime) -> None:
    """Materialize due time reminders and advance them only after persistence."""

    for reminder in await get_due_reminders(now):
        reminder_id = str(reminder.get("reminder_id") or "")
        due_at = reminder.get("due_at")
        if not reminder_id or not due_at:
            continue
        related_id = f"{reminder_id}_{due_at}"
        try:
            await create_message(
                trigger_type="reminder",
                text=str(reminder.get("text") or "Reminder"),
                related_id=related_id,
            )
            await mark_done(reminder_id, now=now)
        except Exception:
            logger.exception("Due reminder trigger failed for %s", reminder_id)


def _day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time.min, tzinfo=LOCAL_TZ)
    return start, start + dt.timedelta(days=1)


def _is_today_reminder(reminder: dict[str, Any], today: dt.date) -> bool:
    if reminder.get("trigger_type") == "time":
        due_at = reminder.get("due_at")
        if isinstance(due_at, str):
            try:
                due_at = dt.datetime.fromisoformat(due_at)
            except ValueError:
                return False
        return isinstance(due_at, dt.datetime) and to_local(due_at).date() == today
    trigger = reminder.get("event_trigger") or {}
    valid_date = trigger.get("valid_date")
    return valid_date in (None, today, today.isoformat())


def _limit_to_three_sentences(text: str) -> str:
    cleaned = " ".join(text.split())
    sentences = [
        sentence for sentence in re.split(r"(?<=[.!?])\s+", cleaned) if sentence
    ]
    return " ".join(sentences[:3])


async def maybe_morning_report(event_timestamp: dt.datetime) -> None:
    """Create one first-event report for the event's local calendar date."""

    local_timestamp = to_local(event_timestamp)
    today = local_timestamp.date()
    related_id = f"morning_{today.isoformat()}"
    if await _message_for_related_id(related_id):
        return

    start, end = _day_bounds(today)
    event_count = await get_events_collection().count_documents(
        {"timestamp": {"$gte": start, "$lt": end}}, limit=2
    )
    if event_count > 1:
        return

    yesterday = today - dt.timedelta(days=1)
    summaries = [
        document
        async for document in get_memory_summaries_collection()
        .find({"date": yesterday.isoformat()})
        .sort("room_number", 1)
    ]
    active_reminders = await list_active_reminders()
    today_reminders = [
        reminder
        for reminder in active_reminders
        if _is_today_reminder(reminder, today)
    ]
    pinned_safety_facts = [
        fact
        for fact in await get_active_facts()
        if fact.get("pinned") and fact.get("category") == "safety"
    ]

    report = await invoke_structured(
        prompt={
            "today": today.isoformat(),
            "yesterday_memories": [
                str(summary.get("text") or "") for summary in summaries
            ]
            or ["It was a quiet day yesterday."],
            "today_reminders": [
                str(reminder.get("text") or "") for reminder in today_reminders
            ],
            "pinned_safety_facts": [
                str(fact.get("text") or "") for fact in pinned_safety_facts
            ],
        },
        output_model=MorningReportText,
        system_prompt=with_patient_answer_context(
            "Write a warm, calm morning check-in of at most three short sentences. "
            "Mention only supplied memories, reminders, and safety facts. Do not "
            "mention cameras, monitoring, databases, or internal reasoning."
        ),
        structured_output_prompt="Return the complete report in the text field.",
        max_tokens=250,
        task="synthesis",
    )
    await create_message(
        trigger_type="morning_report",
        text=_limit_to_three_sentences(report.text),
        related_id=related_id,
    )


async def maybe_event_reminders(event: Any) -> None:
    """Match active event reminders against one newly persisted memory event."""

    local_timestamp = to_local(event.timestamp)
    local_date = local_timestamp.date().isoformat()
    reminders = await get_matchable_event_reminders(
        local_timestamp, room_number=event.room_number
    )
    for reminder in reminders:
        reminder_id = str(reminder.get("reminder_id") or "")
        if not reminder_id:
            continue
        related_id = f"{reminder_id}_{local_date}"
        try:
            if await _message_for_related_id(related_id):
                continue
            matches = True
            if get_provider_settings().event_reminder_llm_match:
                trigger = reminder.get("event_trigger") or {}
                try:
                    decision = await invoke_structured(
                        prompt={
                            "event": event.semantic_text,
                            "condition": str(trigger.get("condition") or ""),
                        },
                        output_model=EventReminderMatch,
                        system_prompt=(
                            "Judge only whether the supplied home event satisfies "
                            "the reminder condition. Stay literal and do not infer "
                            "actions that are absent from the event."
                        ),
                        structured_output_prompt=(
                            "Return matches and one short factual reason."
                        ),
                        max_tokens=150,
                        task="judge",
                    )
                    matches = decision.matches
                except Exception:
                    logger.exception(
                        "Event reminder judge failed for %s; using deterministic fallback",
                        reminder_id,
                    )
                    matches = True
            if not matches:
                continue

            await create_message(
                trigger_type="reminder",
                text=str(reminder.get("text") or "Reminder"),
                related_id=related_id,
            )
            trigger = reminder.get("event_trigger") or {}
            if trigger.get("valid_date") is not None:
                await mark_done(reminder_id, now=local_timestamp)
        except Exception:
            logger.exception("Event reminder trigger failed for %s", reminder_id)
