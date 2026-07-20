from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .db_client import (
    get_events_collection,
    get_memory_digests_collection,
    get_memory_summaries_collection,
)
from .llm.client import invoke_structured
from .llm.model_registry import get_model_registry
from .llm.prompt_context import with_patient_answer_context
from .memory_schema import memory_event_from_mongo
from .prompt_budget import compact_json_records, truncate_text
from .timezone_utils import LOCAL_TZ, now_local, to_local


logger = logging.getLogger(__name__)
DIGEST_EVENT_LIMIT = 12
DIGEST_PROMPT_BUDGET_CHARS = 8_000
PUBLIC_FIELDS = (
    "digest_id",
    "date",
    "text",
    "highlights",
    "source_summary_count",
    "source_event_count",
    "created_at",
    "updated_at",
)


class DailyDigestText(BaseModel):
    text: str = Field(min_length=1)
    highlights: list[str] = Field(default_factory=list)


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


def _serialize_digest(document: dict[str, Any]) -> dict[str, Any]:
    return {
        field: _json_safe(document.get(field))
        for field in PUBLIC_FIELDS
    }


def _limit_sentences(text: str, limit: int = 4) -> str:
    cleaned = " ".join(str(text or "").split())
    sentences = [
        sentence
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence
    ]
    return " ".join(sentences[:limit])


def _clean_highlights(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        highlight = " ".join(str(value or "").split())
        if highlight and highlight not in cleaned:
            cleaned.append(truncate_text(highlight, 140))
        if len(cleaned) == 3:
            break
    return cleaned


def _source_fingerprint(
    summaries: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> str:
    source_ids = sorted(
        [f"summary:{item['summary_id']}" for item in summaries]
        + [f"event:{item['event_id']}" for item in events]
    )
    return hashlib.sha256("|".join(source_ids).encode("utf-8")).hexdigest()


class DailyDigestService:
    def __init__(
        self,
        *,
        events_collection=None,
        summaries_collection=None,
        digests_collection=None,
    ):
        self._events_collection = events_collection
        self._summaries_collection = summaries_collection
        self._digests_collection = digests_collection

    @property
    def events_collection(self):
        if self._events_collection is not None:
            return self._events_collection
        return get_events_collection()

    @property
    def summaries_collection(self):
        if self._summaries_collection is not None:
            return self._summaries_collection
        return get_memory_summaries_collection()

    @property
    def digests_collection(self):
        if self._digests_collection is not None:
            return self._digests_collection
        return get_memory_digests_collection()

    async def get_digests(
        self,
        days: int = 7,
        *,
        now: Optional[dt.datetime] = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        capped_days = max(1, min(31, int(days)))
        today = to_local(now or now_local()).date()
        results = await asyncio.gather(
            *(
                self._digest_for_day(
                    today - dt.timedelta(days=offset),
                    force=force,
                )
                for offset in range(capped_days)
            ),
            return_exceptions=True,
        )
        digests: list[dict[str, Any]] = []
        for offset, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Daily digest failed for %s",
                    today - dt.timedelta(days=offset),
                    exc_info=(type(result), result, result.__traceback__),
                )
            elif result is not None:
                digests.append(result)
        return sorted(digests, key=lambda item: item["date"], reverse=True)

    async def _digest_for_day(
        self,
        day: dt.date,
        *,
        force: bool,
    ) -> Optional[dict[str, Any]]:
        existing = await self.digests_collection.find_one(
            {"date": day.isoformat()}
        )
        try:
            summaries, events = await self._gather_sources(day)
            if not summaries and not events:
                return None

            fingerprint = _source_fingerprint(summaries, events)
            if (
                existing is not None
                and existing.get("source_fingerprint") == fingerprint
                and not force
            ):
                logger.info("Daily digest cache hit for %s", day.isoformat())
                return _serialize_digest(existing)

            generated = await invoke_structured(
                prompt={
                    "date": day.isoformat(),
                    "memory_summaries": summaries,
                    "recent_moments": events,
                },
                output_model=DailyDigestText,
                system_prompt=with_patient_answer_context(
                    "Write a warm recap of this day in two to four short sentences. "
                    "Use first or second person and only the supplied material. "
                    "Return up to three short highlights. Never mention cameras, "
                    "monitoring, databases, source records, or internal reasoning. "
                    "Do not invent details."
                ),
                model_id=get_model_registry().synthesis,
                structured_output_prompt=(
                    "Return the recap in text and zero to three short highlights."
                ),
                max_tokens=400,
                task="synthesis",
            )
            timestamp = now_local()
            digest_id = f"dig_{day.isoformat()}"
            text = _limit_sentences(generated.text, 4)
            highlights = _clean_highlights(generated.highlights)
            update = {
                "$set": {
                    "digest_id": digest_id,
                    "date": day.isoformat(),
                    "text": text,
                    "highlights": highlights,
                    "source_fingerprint": fingerprint,
                    "source_summary_count": len(summaries),
                    "source_event_count": len(events),
                    "updated_at": timestamp,
                },
                "$setOnInsert": {"created_at": timestamp},
            }
            await self.digests_collection.update_one(
                {"date": day.isoformat()},
                update,
                upsert=True,
            )
            logger.info("Daily digest generated for %s", day.isoformat())
            return _serialize_digest(
                {
                    **update["$set"],
                    "created_at": (
                        existing.get("created_at")
                        if existing is not None
                        else timestamp
                    ),
                }
            )
        except Exception:
            logger.exception("Daily digest generation failed for %s", day.isoformat())
            if existing is not None:
                return _serialize_digest(existing)
            return None

    async def _gather_sources(
        self,
        day: dt.date,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        summary_documents = [
            document
            async for document in self.summaries_collection.find(
                {"date": day.isoformat()}
            ).sort("room_number", 1)
        ]
        summary_budget = DIGEST_PROMPT_BUDGET_CHARS // 2
        per_summary = max(
            180,
            summary_budget // max(1, len(summary_documents)),
        )
        summaries = compact_json_records(
            [
                {
                    "summary_id": str(
                        document.get("summary_id") or document.get("_id") or ""
                    ),
                    "room_name": str(document.get("room_name") or ""),
                    "memory": truncate_text(document.get("text"), per_summary),
                }
                for document in summary_documents
            ],
            max_chars=summary_budget,
        )

        start = dt.datetime.combine(day, dt.time.min, tzinfo=LOCAL_TZ)
        end = start + dt.timedelta(days=1)
        active_events = []
        async for document in self.events_collection.find(
            {"timestamp": {"$gte": start, "$lt": end}}
        ):
            event = memory_event_from_mongo(document)
            if event.lifecycle_status == "active":
                active_events.append(event)
        active_events.sort(
            key=lambda event: (-event.importance, event.timestamp, event.event_id)
        )
        active_events = active_events[:DIGEST_EVENT_LIMIT]

        rendered_summaries = len(json.dumps(summaries, ensure_ascii=False))
        event_budget = max(
            1_000,
            DIGEST_PROMPT_BUDGET_CHARS - rendered_summaries - 500,
        )
        per_event = max(180, event_budget // max(1, len(active_events)))
        events = compact_json_records(
            [
                {
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                    "room_name": event.room_name,
                    "memory": truncate_text(event.semantic_text, per_event),
                }
                for event in active_events
            ],
            max_chars=event_budget,
        )
        return summaries, events


_default_service = DailyDigestService()


async def get_daily_digests(
    days: int = 7,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    return await _default_service.get_digests(days, force=force)
