"""Run the real API against isolated spec-0006 Mongo collections.

This rehearsal server is intentionally separate from the production entrypoint so
live validation never writes synthetic chat/profile/reminder data to production
collections. It uses the configured live LLM provider and otherwise serves the
normal FastAPI application.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Blue_dream_agents import api, conversation_memory, profile_memory, reminder_service
from Blue_dream_agents.db_client import get_mongo_client


database = get_mongo_client().dementia_assistance
conversation_collection = database.spec0006_smoke_conversation_sessions
profile_collection = database.spec0006_smoke_profile_facts
reminder_collection = database.spec0006_smoke_reminders

conversation_memory._default_store = conversation_memory.ConversationMemoryStore(
    conversation_collection
)
profile_memory._default_service = profile_memory.ProfileMemoryService(profile_collection)
reminder_service._default_service = reminder_service.ReminderService(reminder_collection)


async def _noop_indexes() -> None:
    return None


async def _conversation_indexes() -> None:
    await conversation_collection.create_index("session_id", unique=True)


async def _profile_indexes() -> None:
    await profile_collection.create_index([("status", 1), ("category", 1)])


async def _reminder_indexes() -> None:
    await reminder_collection.create_index([("status", 1), ("due_at", 1)])
    await reminder_collection.create_index([("status", 1), ("trigger_type", 1)])


api.ensure_events_indexes = _noop_indexes
api.initialize_alert_indexes = _noop_indexes
api.ensure_conversation_indexes = _conversation_indexes
api.ensure_profile_indexes = _profile_indexes
api.ensure_reminder_indexes = _reminder_indexes


if __name__ == "__main__":
    uvicorn.run(api.app, host="127.0.0.1", port=8016, log_level="warning")
