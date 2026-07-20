from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from .db_client import get_reminders_collection
    from .timezone_utils import LOCAL_TZ, now_local, to_local
except ImportError:
    from db_client import get_reminders_collection
    from timezone_utils import LOCAL_TZ, now_local, to_local


logger = logging.getLogger(__name__)
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class EventTrigger(BaseModel):
    room_number: Optional[int] = None
    window_start: str
    window_end: str
    condition: str = Field(min_length=1)
    valid_date: Optional[dt.date] = None

    @field_validator("window_start", "window_end")
    @classmethod
    def validate_window_time(cls, value: str) -> str:
        if not TIME_PATTERN.fullmatch(value):
            raise ValueError("event windows must use HH:MM local time")
        return value

    @field_validator("condition")
    @classmethod
    def clean_condition(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("event condition is required")
        return cleaned


class ReminderExtraction(BaseModel):
    is_reminder: bool = False
    text: Optional[str] = None
    trigger_type: Optional[Literal["time", "event"]] = None
    due_at: Optional[dt.datetime] = None
    recurrence: Literal["none", "daily"] = "none"
    event_trigger: Optional[EventTrigger] = None

    @model_validator(mode="after")
    def validate_extracted_reminder(self):
        if not self.is_reminder:
            return self
        if not self.text or not self.text.strip():
            raise ValueError("reminder text is required")
        if self.trigger_type == "time":
            if self.due_at is None:
                raise ValueError("time reminders require due_at")
            if self.event_trigger is not None:
                raise ValueError("time reminders cannot include event_trigger")
        elif self.trigger_type == "event":
            if self.event_trigger is None:
                raise ValueError("event reminders require event_trigger")
            if self.due_at is not None:
                raise ValueError("event reminders cannot include due_at")
            if self.recurrence != "none":
                raise ValueError("event reminders do not use recurrence")
        else:
            raise ValueError("reminder trigger_type is required")
        return self


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1)
    trigger_type: Literal["time", "event"] = "time"
    due_at: Optional[dt.datetime] = None
    recurrence: Literal["none", "daily"] = "none"
    event_trigger: Optional[EventTrigger] = None

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reminder text is required")
        return cleaned

    @model_validator(mode="after")
    def validate_trigger_shape(self):
        if self.trigger_type == "time":
            if self.due_at is None:
                raise ValueError("time reminders require due_at")
            if self.event_trigger is not None:
                raise ValueError("time reminders cannot include event_trigger")
        else:
            if self.event_trigger is None:
                raise ValueError("event reminders require event_trigger")
            if self.due_at is not None:
                raise ValueError("event reminders cannot include due_at")
            if self.recurrence != "none":
                raise ValueError("event reminders require recurrence='none'")
        return self


def _normalize_due_at(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(LOCAL_TZ)


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


def serialize_reminder(document: dict[str, Any]) -> dict[str, Any]:
    serialized = _json_safe(document)
    serialized.pop("_id", None)
    return serialized


def _window_contains(local_time: dt.time, start: str, end: str) -> bool:
    current = local_time.strftime("%H:%M")
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


class ReminderService:
    def __init__(self, collection=None):
        self._injected_collection = collection

    @property
    def collection(self):
        if self._injected_collection is not None:
            return self._injected_collection
        return get_reminders_collection()

    async def create(
        self,
        reminder: ReminderCreate,
        *,
        source: Literal["chat", "api"] = "api",
        origin_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        now = now_local()
        object_id = ObjectId()
        event_trigger = (
            reminder.event_trigger.model_dump(mode="json")
            if reminder.event_trigger is not None
            else None
        )
        document: dict[str, Any] = {
            "_id": object_id,
            "reminder_id": str(object_id),
            "text": reminder.text,
            "trigger_type": reminder.trigger_type,
            "due_at": (
                _normalize_due_at(reminder.due_at)
                if reminder.due_at is not None
                else None
            ),
            "recurrence": reminder.recurrence,
            "event_trigger": event_trigger,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "source": source,
            "origin_context": origin_context,
        }
        await self.collection.insert_one(document)
        return serialize_reminder(document)

    async def list_active(self) -> list[dict[str, Any]]:
        cursor = self.collection.find({"status": "active"}).sort("created_at", -1)
        return [serialize_reminder(document) async for document in cursor]

    async def get_today(
        self,
        now: Optional[dt.datetime] = None,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return a small, indexed working-memory view of today's reminders."""

        capped_limit = max(0, int(limit))
        if capped_limit == 0:
            return []

        local_now = to_local(now or now_local())
        start = dt.datetime.combine(local_now.date(), dt.time.min, tzinfo=LOCAL_TZ)
        end = start + dt.timedelta(days=1)
        time_cursor = (
            self.collection.find(
                {
                    "status": "active",
                    "trigger_type": "time",
                    "due_at": {"$gte": start, "$lt": end},
                }
            )
            .sort("due_at", 1)
            .limit(capped_limit)
        )
        reminders = [serialize_reminder(document) async for document in time_cursor]

        remaining = capped_limit - len(reminders)
        if remaining <= 0:
            return reminders
        today = local_now.date().isoformat()
        event_cursor = (
            self.collection.find(
                {
                    "status": "active",
                    "trigger_type": "event",
                    "event_trigger.valid_date": {"$in": [None, today]},
                }
            )
            .sort("created_at", 1)
            .limit(remaining)
        )
        reminders.extend(
            [serialize_reminder(document) async for document in event_cursor]
        )
        return reminders

    async def mark_done(
        self,
        reminder_id: str,
        *,
        mode: Literal["delivery", "patient"],
        now: Optional[dt.datetime] = None,
    ) -> bool:
        document = await self.collection.find_one(
            {"reminder_id": reminder_id, "status": "active"}
        )
        if not document:
            return False

        completed_at = to_local(now or now_local())
        is_recurring_time = (
            document.get("trigger_type") == "time"
            and document.get("recurrence") == "daily"
            and isinstance(document.get("due_at"), dt.datetime)
        )
        if is_recurring_time:
            next_due = to_local(document["due_at"])
            if mode == "patient" and next_due > completed_at:
                next_due += dt.timedelta(days=1)
            while next_due <= completed_at:
                next_due += dt.timedelta(days=1)
            update = {
                "$set": {
                    "due_at": next_due,
                    "last_completed_at": completed_at,
                    "updated_at": completed_at,
                }
            }
        elif mode == "patient":
            update = {
                "$set": {
                    "status": "archived",
                    "completed_at": completed_at,
                    "archived_at": completed_at,
                    "updated_at": completed_at,
                }
            }
        else:
            update = {
                "$set": {
                    "status": "done",
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                }
            }
        result = await self.collection.update_one(
            {"reminder_id": reminder_id, "status": "active"}, update
        )
        return bool(result.matched_count)

    async def archive(
        self,
        reminder_id: str,
        *,
        now: Optional[dt.datetime] = None,
    ) -> bool:
        archived_at = to_local(now or now_local())
        result = await self.collection.update_one(
            {"reminder_id": reminder_id, "status": "active"},
            {
                "$set": {
                    "status": "archived",
                    "archived_at": archived_at,
                    "updated_at": archived_at,
                }
            },
        )
        return bool(result.matched_count)

    async def get_due(self, now: dt.datetime) -> list[dict[str, Any]]:
        local_now = to_local(now)
        cursor = self.collection.find(
            {
                "status": "active",
                "trigger_type": "time",
                "due_at": {"$lte": local_now},
            }
        ).sort("due_at", 1)
        return [serialize_reminder(document) async for document in cursor]

    async def get_matchable_events(
        self, now: dt.datetime, *, room_number: Optional[int] = None
    ) -> list[dict[str, Any]]:
        local_now = to_local(now)
        today = local_now.date().isoformat()
        query: dict[str, Any] = {
            "status": "active",
            "trigger_type": "event",
            "event_trigger.valid_date": {"$in": [None, today]},
        }
        if room_number is not None:
            query["event_trigger.room_number"] = {"$in": [None, room_number]}
        cursor = self.collection.find(query)
        results: list[dict[str, Any]] = []
        async for document in cursor:
            trigger = document.get("event_trigger") or {}
            start = str(trigger.get("window_start") or "")
            end = str(trigger.get("window_end") or "")
            if TIME_PATTERN.fullmatch(start) and TIME_PATTERN.fullmatch(end):
                if _window_contains(local_now.time(), start, end):
                    results.append(serialize_reminder(document))
        return results


_default_service = ReminderService()


async def create_reminder(
    reminder: ReminderCreate,
    *,
    source: Literal["chat", "api"] = "api",
    origin_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return await _default_service.create(
        reminder, source=source, origin_context=origin_context
    )


async def list_active() -> list[dict[str, Any]]:
    return await _default_service.list_active()


async def mark_done(
    reminder_id: str,
    *,
    mode: Literal["delivery", "patient"],
    now: Optional[dt.datetime] = None,
) -> bool:
    return await _default_service.mark_done(reminder_id, mode=mode, now=now)


async def archive_reminder(
    reminder_id: str,
    *,
    now: Optional[dt.datetime] = None,
) -> bool:
    return await _default_service.archive(reminder_id, now=now)


async def get_today_reminders(
    now: Optional[dt.datetime] = None, *, limit: int = 5
) -> list[dict[str, Any]]:
    return await _default_service.get_today(now, limit=limit)


async def render_today_reminder_block(
    now: Optional[dt.datetime] = None, *, limit: int = 5
) -> str:
    """Render today's active reminders for patient-answer working memory."""

    try:
        reminders = await get_today_reminders(now, limit=limit)
    except Exception:
        logger.exception("Today's reminder working-memory read failed")
        return ""

    lines: list[str] = []
    for reminder in reminders[: max(0, limit)]:
        text = " ".join(str(reminder.get("text") or "").split())
        if not text:
            continue
        if reminder.get("trigger_type") == "time":
            due_at = reminder.get("due_at")
            if isinstance(due_at, str):
                try:
                    due_at = dt.datetime.fromisoformat(due_at)
                except ValueError:
                    due_at = None
            if isinstance(due_at, dt.datetime):
                due_text = to_local(due_at).strftime("%I:%M %p").lstrip("0")
                lines.append(f"- Reminder: {text} (due {due_text})")
                continue
        lines.append(f"- Reminder: {text}")

    if not lines:
        return ""
    return "Today's active reminders:\n" + "\n".join(lines)


async def get_due_reminders(now: dt.datetime) -> list[dict[str, Any]]:
    return await _default_service.get_due(now)


async def get_matchable_event_reminders(
    now: dt.datetime, *, room_number: Optional[int] = None
) -> list[dict[str, Any]]:
    return await _default_service.get_matchable_events(
        now, room_number=room_number
    )
