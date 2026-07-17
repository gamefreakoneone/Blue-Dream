import os
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/Los_Angeles"))


def now_local() -> datetime:
    """Get current time in local timezone (timezone-aware)."""
    return datetime.now(LOCAL_TZ)


# print(now_local())
