"""Shared MongoDB client singleton for all Blue Dream agent modules.

Centralizes connection management to avoid duplicate AsyncIOMotorClient instances
across object_detector, time_agent, and semantic_search.
"""

from __future__ import annotations

import os
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
        _mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
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
