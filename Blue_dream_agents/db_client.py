"""Shared MongoDB client singleton for all Blue Dream agent modules.

Centralizes connection management to avoid duplicate AsyncIOMotorClient instances
across object_detector, time_agent, and semantic_search.
"""

from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

try:
    from .llm.settings import get_provider_settings
except ImportError:
    from llm.settings import get_provider_settings


_mongo_client: Optional[AsyncIOMotorClient] = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Return the shared MongoDB async client (created on first call)."""
    global _mongo_client
    if _mongo_client is None:
        settings = get_provider_settings()
        _mongo_client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=3000,
        )
    return _mongo_client


async def close_mongo_client() -> None:
    """Close the shared MongoDB client (call on shutdown)."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


def get_events_collection():
    """Shortcut: return the dementia_assistance.events collection."""
    return get_mongo_client().dementia_assistance.events


def get_safety_alerts_collection():
    """Shortcut: return the dementia_assistance.safety_alerts collection."""
    return get_mongo_client().dementia_assistance.safety_alerts


def get_devices_collection():
    """Shortcut: return the dementia_assistance.devices collection."""
    return get_mongo_client().dementia_assistance.devices


def get_geofence_collection():
    """Shortcut: return the dementia_assistance.geofence_settings collection."""
    return get_mongo_client().dementia_assistance.geofence_settings


def get_conversation_sessions_collection():
    """Return the durable patient conversation collection."""
    return get_mongo_client().dementia_assistance.conversation_sessions


def get_profile_facts_collection():
    """Return the durable patient profile-fact collection."""
    return get_mongo_client().dementia_assistance.profile_facts


def get_reminders_collection():
    """Return the durable reminder collection."""
    return get_mongo_client().dementia_assistance.reminders


def get_memory_summaries_collection():
    """Return day-level consolidated memory summaries."""
    return get_mongo_client().dementia_assistance.memory_summaries


async def ensure_events_indexes() -> None:
    """Create MongoDB indexes used by ingestion and retrieval paths."""

    collection = get_events_collection()
    await collection.create_index([("timestamp", 1)], name="timestamp_1")
    await collection.create_index(
        [("room_number", 1), ("timestamp", -1)],
        name="room_number_1_timestamp_-1",
    )
    await collection.create_index([("event_id", 1)], name="event_id_1")
    await collection.create_index([("video_path", 1)], name="video_path_1")
    await collection.create_index(
        [
            ("lifecycle_status", 1),
            ("pinned", 1),
            ("importance", 1),
            ("timestamp", 1),
        ],
        name="lifecycle_status_1_pinned_1_importance_1_timestamp_1",
    )


async def ensure_memory_lifecycle_indexes() -> None:
    """Create indexes used by deterministic day-level consolidation."""

    summaries = get_memory_summaries_collection()
    await summaries.create_index(
        [("summary_id", 1)], name="summary_id_1", unique=True
    )
    await summaries.create_index(
        [("date", -1), ("room_number", 1)],
        name="date_-1_room_number_1",
    )


async def ensure_alert_indexes() -> None:
    """Create MongoDB indexes used by mobile alert and device endpoints."""

    alerts = get_safety_alerts_collection()
    await alerts.create_index([("alert_id", 1)], name="alert_id_1", unique=True)
    await alerts.create_index([("status", 1), ("created_at", -1)], name="status_1_created_at_-1")
    await alerts.create_index(
        [("target_role", 1), ("status", 1), ("created_at", -1)],
        name="target_role_1_status_1_created_at_-1",
    )
    await alerts.create_index([("event_id", 1)], name="event_id_1")

    devices = get_devices_collection()
    await devices.create_index([("device_id", 1)], name="device_id_1", unique=True)
    await devices.create_index([("role", 1), ("enabled", 1)], name="role_1_enabled_1")

    geofence = get_geofence_collection()
    await geofence.create_index([("config_id", 1)], name="config_id_1", unique=True)


async def ensure_conversation_indexes() -> None:
    """Create indexes for Mongo-backed conversation sessions."""

    await get_conversation_sessions_collection().create_index(
        [("session_id", 1)], name="session_id_1", unique=True
    )


async def ensure_profile_indexes() -> None:
    """Create indexes used to inject and deduplicate active profile facts."""

    await get_profile_facts_collection().create_index(
        [("status", 1), ("category", 1)],
        name="status_1_category_1",
    )


async def ensure_reminder_indexes() -> None:
    """Create indexes used by time and event reminder pre-filters."""

    reminders = get_reminders_collection()
    await reminders.create_index(
        [("status", 1), ("due_at", 1)],
        name="status_1_due_at_1",
    )
    await reminders.create_index(
        [("status", 1), ("trigger_type", 1)],
        name="status_1_trigger_type_1",
    )
