import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/Los_Angeles"))


def now_local() -> datetime:
    """Get current time in local timezone (timezone-aware)."""
    return datetime.now(LOCAL_TZ)


def to_local(value: datetime) -> datetime:
    """Normalize an aware or Mongo-returned naive UTC datetime to project time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ)


# print(now_local())
