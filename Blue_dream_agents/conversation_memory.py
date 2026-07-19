from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

try:
    from .db_client import get_conversation_sessions_collection
    from .llm.client import invoke_structured
    from .llm.model_registry import get_model_registry
    from .timezone_utils import now_local
except ImportError:
    from db_client import get_conversation_sessions_collection
    from llm.client import invoke_structured
    from llm.model_registry import get_model_registry
    from timezone_utils import now_local


logger = logging.getLogger(__name__)

DEFAULT_MAX_TURNS = 12
MAX_CONTEXT_CHARS = 4000


class ConversationSummary(BaseModel):
    summary: str = Field(default="", description="Compact merged conversation summary")


def _normalize_session_id(session_id: Optional[str]) -> Optional[str]:
    if session_id is None:
        return None
    normalized = session_id.strip()
    return normalized or None


def _configured_max_turns() -> int:
    try:
        return max(1, int(os.getenv("CONVERSATION_MAX_TURNS", str(DEFAULT_MAX_TURNS))))
    except ValueError:
        logger.warning(
            "Invalid CONVERSATION_MAX_TURNS; using default %d",
            DEFAULT_MAX_TURNS,
        )
        return DEFAULT_MAX_TURNS


def _render_context(document: dict) -> str:
    summary = " ".join(str(document.get("summary") or "").split())
    turns = document.get("turns") or []

    lines: list[str] = []
    exchange_number = 0
    for turn in turns:
        role = str(turn.get("role") or "").strip().lower()
        text = " ".join(str(turn.get("text") or "").split())
        if not text or role not in {"user", "assistant"}:
            continue
        if role == "user" or exchange_number == 0:
            exchange_number += 1
        lines.append(f"Turn {exchange_number} {role}: {text}")

    summary_section = (
        f"Earlier in this conversation: {summary}" if summary else ""
    )
    rendered_turns = "\n".join(lines)
    rendered = "\n".join(part for part in (summary_section, rendered_turns) if part)
    if len(rendered) <= MAX_CONTEXT_CHARS:
        return rendered

    # Preserve the durable summary and pack the newest complete turn lines.
    if len(summary_section) > MAX_CONTEXT_CHARS // 2:
        summary_section = (
            "Earlier in this conversation: …"
            + summary_section[-(MAX_CONTEXT_CHARS // 2) :]
        )
    available = MAX_CONTEXT_CHARS - len(summary_section) - (1 if summary_section else 0)
    newest_lines: list[str] = []
    used = 0
    for line in reversed(lines):
        cost = len(line) + (1 if newest_lines else 0)
        if used + cost > available:
            break
        newest_lines.append(line)
        used += cost
    newest_lines.reverse()
    return "\n".join(
        part for part in (summary_section, "\n".join(newest_lines)) if part
    )[-MAX_CONTEXT_CHARS:]


class ConversationMemoryStore:
    """Mongo-backed conversation storage with an invalidated-on-write read cache."""

    def __init__(self, collection=None, *, max_turns: Optional[int] = None):
        self._injected_collection = collection
        self.max_turns = max_turns if max_turns is not None else _configured_max_turns()
        self._context_cache: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def collection(self):
        if self._injected_collection is not None:
            return self._injected_collection
        return get_conversation_sessions_collection()

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    async def get_context(self, session_id: Optional[str]) -> str:
        normalized_id = _normalize_session_id(session_id)
        if normalized_id is None:
            return ""
        if normalized_id in self._context_cache:
            return self._context_cache[normalized_id]

        document = await self.collection.find_one({"session_id": normalized_id})
        if not document or document.get("status") == "closed":
            return ""
        rendered = _render_context(document)
        self._context_cache[normalized_id] = rendered
        return rendered

    async def append_turn(
        self,
        session_id: Optional[str],
        role: Literal["user", "assistant"],
        text: str,
    ) -> bool:
        normalized_id = _normalize_session_id(session_id)
        if normalized_id is None:
            return False
        cleaned_text = text.strip()
        if not cleaned_text:
            return False

        async with self._lock_for(normalized_id):
            existing = await self.collection.find_one({"session_id": normalized_id})
            if existing and existing.get("status") == "closed":
                return False

            now = now_local()
            await self.collection.update_one(
                {"session_id": normalized_id},
                {
                    "$push": {
                        "turns": {"role": role, "text": cleaned_text, "ts": now}
                    },
                    "$set": {"last_active_at": now},
                    "$setOnInsert": {
                        "summary": "",
                        "summary_updated_at": None,
                        "status": "active",
                        "created_at": now,
                    },
                },
                upsert=True,
            )
            self._context_cache.pop(normalized_id, None)
            await self._compact_if_needed(normalized_id)
        return True

    async def _compact_if_needed(self, session_id: str) -> None:
        document = await self.collection.find_one({"session_id": session_id})
        if not document or document.get("status") == "closed":
            return
        turns = list(document.get("turns") or [])
        overflow_count = len(turns) - self.max_turns
        if overflow_count <= 0:
            return

        overflow = turns[:overflow_count]
        try:
            summary = await self._summarize(
                previous_summary=str(document.get("summary") or ""),
                overflow_turns=overflow,
            )
        except Exception:
            logger.exception(
                "Conversation summarization failed for session %s; turns retained",
                session_id,
            )
            return

        now = now_local()
        await self.collection.update_one(
            {"session_id": session_id, "status": {"$ne": "closed"}},
            {
                "$set": {
                    "summary": summary,
                    "summary_updated_at": now,
                    "turns": turns[overflow_count:],
                }
            },
        )
        self._context_cache.pop(session_id, None)

    async def _summarize(
        self, *, previous_summary: str, overflow_turns: list[dict]
    ) -> str:
        result = await invoke_structured(
            prompt={
                "previous_summary": previous_summary,
                "older_turns_to_merge": [
                    {
                        "role": turn.get("role"),
                        "text": turn.get("text"),
                    }
                    for turn in overflow_turns
                ],
            },
            output_model=ConversationSummary,
            system_prompt=(
                "Summarize a patient-assistant conversation for future follow-up "
                "interpretation. Preserve names, relationships, preferences, "
                "commitments, and unresolved references. Do not invent facts."
            ),
            model_id=get_model_registry().synthesis,
            structured_output_prompt=(
                "Return one concise merged summary that incorporates the previous "
                "summary and the supplied older turns."
            ),
            max_tokens=500,
        )
        return result.summary.strip()

    async def reset(self, session_id: Optional[str]) -> bool:
        normalized_id = _normalize_session_id(session_id)
        if normalized_id is None:
            return False
        result = await self.collection.update_one(
            {"session_id": normalized_id},
            {"$set": {"status": "closed", "last_active_at": now_local()}},
        )
        self._context_cache.pop(normalized_id, None)
        return bool(result.matched_count)


_default_store = ConversationMemoryStore()


async def get_conversation_context(session_id: Optional[str]) -> str:
    return await _default_store.get_context(session_id)


async def append_conversation_turn(
    session_id: Optional[str],
    role: Literal["user", "assistant"],
    text: str,
) -> bool:
    return await _default_store.append_turn(session_id, role, text)


async def reset_conversation(session_id: Optional[str]) -> bool:
    return await _default_store.reset(session_id)
