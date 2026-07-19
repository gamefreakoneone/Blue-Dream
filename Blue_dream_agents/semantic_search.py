from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

try:
    from .db_client import get_mongo_client, close_mongo_client
    from .llm.client import embed_texts, invoke_text
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from .llm.settings import get_provider_settings
    from .memory_schema import MemoryEvent, memory_event_from_mongo
    from .memory_schema import normalize_timestamp
    from .profile_memory import get_active_facts
    from .prompt_budget import RecallCandidate, RecallPack, pack_recall
    from .timezone_utils import LOCAL_TZ, now_local
    from .vector_store import (
        count_indexed_events,
        delete_event_ids,
        get_embedding_metadata,
        get_event_collection_name,
        list_indexed_event_ids,
        query_similar_embeddings,
        reset_active_event_collection,
        upsert_event_embedding,
        upsert_summary_embedding,
    )
except ImportError:
    from db_client import get_mongo_client, close_mongo_client
    from llm.client import embed_texts, invoke_text
    from llm.model_registry import get_model_registry
    from llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from llm.settings import get_provider_settings
    from memory_schema import MemoryEvent, memory_event_from_mongo
    from memory_schema import normalize_timestamp
    from profile_memory import get_active_facts
    from prompt_budget import RecallCandidate, RecallPack, pack_recall
    from timezone_utils import LOCAL_TZ, now_local
    from vector_store import (
        count_indexed_events,
        delete_event_ids,
        get_embedding_metadata,
        get_event_collection_name,
        list_indexed_event_ids,
        query_similar_embeddings,
        reset_active_event_collection,
        upsert_event_embedding,
        upsert_summary_embedding,
    )


logger = logging.getLogger(__name__)


class SemanticMatch(BaseModel):
    event_id: str
    memory_type: str = "event"
    score: float
    final_score: float = 0.0
    pinned: bool = False
    timestamp: str
    room_name: str
    semantic_text: str
    audio_transcript: str = ""
    video_description: str = ""
    transcript_length: int = 0
    screenshot_path: Optional[str] = None


class RecallDebugMemory(BaseModel):
    id: str
    type: str
    timestamp: str
    similarity: float
    final_score: float
    pinned: bool


class RecallDebug(BaseModel):
    considered_count: int = 0
    packed_count: int = 0
    excluded_count: int = 0
    memories: list[RecallDebugMemory] = Field(default_factory=list)


class SemanticSearchResult(BaseModel):
    success: bool
    text: str
    query: str
    match_count: int
    top_k: int
    index_status: str = "ready"
    error_code: Optional[str] = None
    matches: List[SemanticMatch] = Field(default_factory=list)
    recall_debug: RecallDebug = Field(default_factory=RecallDebug)


_sync_lock = asyncio.Lock()
_bootstrapped_collection: Optional[str] = None
_last_sync_time: float = 0.0
_SYNC_TTL_SECONDS: float = 60.0  # Skip full index inspection if synced within this window


async def close_clients():
    """Legacy convenience wrapper - delegates to shared db_client."""
    await close_mongo_client()


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


async def index_memory_event(event: MemoryEvent) -> None:
    embeddings = await embed_texts([event.semantic_text])
    embedding = embeddings[0]
    await _run_blocking(upsert_event_embedding, event, embedding)


async def index_memory_summary(summary: dict[str, Any]) -> None:
    embeddings = await embed_texts([str(summary.get("text", ""))])
    await _run_blocking(upsert_summary_embedding, summary, embeddings[0])


async def delete_memory_embeddings(memory_ids: list[str]) -> None:
    await _run_blocking(delete_event_ids, memory_ids)


def _parse_object_ids(event_ids: list[str]) -> list[ObjectId]:
    object_ids: list[ObjectId] = []
    for event_id in event_ids:
        if ObjectId.is_valid(event_id):
            object_ids.append(ObjectId(event_id))
    return object_ids


async def _fetch_events_by_ids(event_ids: list[str]) -> list[MemoryEvent]:
    if not event_ids:
        return []

    collection = get_mongo_client().dementia_assistance.events
    query: Dict[str, Any] = {
        "$or": [
            {"event_id": {"$in": event_ids}},
            {"_id": {"$in": _parse_object_ids(event_ids)}},
        ]
    }

    events_by_id: dict[str, MemoryEvent] = {}
    async for doc in collection.find(query):
        event = memory_event_from_mongo(doc)
        if event.lifecycle_status == "active":
            events_by_id[event.event_id] = event

    return [events_by_id[event_id] for event_id in event_ids if event_id in events_by_id]


async def _fetch_summaries_by_ids(summary_ids: list[str]) -> list[dict[str, Any]]:
    if not summary_ids:
        return []
    collection = get_mongo_client().dementia_assistance.memory_summaries
    by_id: dict[str, dict[str, Any]] = {}
    async for document in collection.find({"summary_id": {"$in": summary_ids}}):
        by_id[str(document.get("summary_id"))] = document
    return [by_id[value] for value in summary_ids if value in by_id]


async def _fetch_pinned_events() -> list[MemoryEvent]:
    collection = get_mongo_client().dementia_assistance.events
    events: list[MemoryEvent] = []
    async for document in collection.find(
        {"pinned": True, "lifecycle_status": {"$ne": "consolidated"}}
    ):
        events.append(memory_event_from_mongo(document))
    return events


async def _count_mongo_events() -> int:
    collection = get_mongo_client().dementia_assistance.events
    return int(await collection.count_documents({}))


async def _indexable_ids() -> set[str]:
    database = get_mongo_client().dementia_assistance
    ids: set[str] = set()
    async for document in database.events.find(
        {"lifecycle_status": {"$ne": "consolidated"}},
        {"event_id": 1},
    ):
        value = document.get("event_id") or document.get("_id")
        if value is not None:
            ids.add(str(value))
    async for document in database.memory_summaries.find({}, {"summary_id": 1}):
        value = document.get("summary_id")
        if value:
            ids.add(str(value))
    return ids


async def _index_all_mongo_events() -> bool:
    database = get_mongo_client().dementia_assistance
    indexed_any = False
    async for doc in database.events.find(
        {"lifecycle_status": {"$ne": "consolidated"}}
    ).sort("timestamp", 1):
        event = memory_event_from_mongo(doc)
        try:
            await index_memory_event(event)
            indexed_any = True
        except Exception as exc:
            logger.warning(
                "Skipping semantic bootstrap for event %s: %s",
                event.event_id,
                exc,
            )
    async for summary in database.memory_summaries.find().sort("date", 1):
        try:
            await index_memory_summary(summary)
            indexed_any = True
        except Exception as exc:
            logger.warning(
                "Skipping semantic bootstrap for summary %s: %s",
                summary.get("summary_id"),
                exc,
            )
    return indexed_any


async def _remove_stale_index_entries() -> int:
    indexed_ids = await _run_blocking(list_indexed_event_ids)
    if not indexed_ids:
        return 0

    existing_ids = await _indexable_ids()
    stale_ids = [event_id for event_id in indexed_ids if event_id not in existing_ids]
    if stale_ids:
        await _run_blocking(delete_event_ids, stale_ids)
    return len(stale_ids)


async def ensure_semantic_index_synced(force_rebuild: bool = False) -> str:
    global _bootstrapped_collection
    global _last_sync_time

    collection_name = get_event_collection_name()

    # TTL short-circuit: skip full inspection if recently synced and not forced
    if (
        not force_rebuild
        and _bootstrapped_collection == collection_name
        and (time.time() - _last_sync_time) < _SYNC_TTL_SECONDS
    ):
        return "ready"

    async with _sync_lock:
        index_status = "ready"
        if force_rebuild:
            logger.warning(
                "Rebuilding active semantic collection %s by request.",
                collection_name,
            )
            await _run_blocking(reset_active_event_collection)
            _bootstrapped_collection = None
            index_status = "reset"

        try:
            indexed_count = await _run_blocking(count_indexed_events)
            indexed_ids = set(await _run_blocking(list_indexed_event_ids))
        except Exception as exc:
            logger.warning(
                "Semantic index health check failed; recreating active collection: %s",
                exc,
            )
            await _run_blocking(reset_active_event_collection)
            indexed_count = 0
            indexed_ids = set()
            index_status = "reset"

        expected_ids = await _indexable_ids()
        mongo_count = len(expected_ids)
        if indexed_count > 0:
            stale_ids = indexed_ids - expected_ids
            if stale_ids:
                await _run_blocking(delete_event_ids, sorted(stale_ids))
                logger.info("Removed %d stale semantic index entries.", len(stale_ids))
                indexed_ids -= stale_ids
            missing_ids = expected_ids - indexed_ids
            if missing_ids:
                logger.info(
                    "Semantic index is missing %s active memories; syncing from Mongo.",
                    len(missing_ids),
                )
                indexed_any = await _index_all_mongo_events()
                _bootstrapped_collection = collection_name
                _last_sync_time = time.time()
                if indexed_any:
                    return "synced" if index_status == "ready" else "recovered"
            _bootstrapped_collection = collection_name
            _last_sync_time = time.time()
            return "ready" if index_status == "ready" else "recovered"

        indexed_any = await _index_all_mongo_events()

        _bootstrapped_collection = collection_name
        _last_sync_time = time.time()
        if indexed_any:
            return "bootstrapped" if index_status == "ready" else "rebuilt"
        return "empty"


def _distance_to_score(distance: float) -> float:
    return 1.0 / (1.0 + max(distance, 0.0))


def _summary_timestamp(summary: dict[str, Any]) -> dt.datetime:
    value = summary.get("date")
    if isinstance(value, dt.datetime):
        return normalize_timestamp(value).replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=LOCAL_TZ)
    try:
        return dt.datetime.combine(dt.date.fromisoformat(str(value)), dt.time.min, tzinfo=LOCAL_TZ)
    except (TypeError, ValueError):
        return normalize_timestamp(summary.get("created_at"))


def _match_from_packed(item, payload: Any) -> SemanticMatch:
    if item.type == "event":
        event: MemoryEvent = payload
        transcript = event.audio_transcript or ""
        room_name = event.room_name
        semantic_text = event.semantic_text
        video_description = event.video_description
        screenshot_path = event.screenshot_path or None
    elif item.type == "summary":
        transcript = ""
        room_name = str(payload.get("room_name", ""))
        semantic_text = str(payload.get("text", ""))
        video_description = ""
        screenshot_path = None
    else:
        transcript = ""
        room_name = ""
        semantic_text = str(payload.get("text", ""))
        video_description = ""
        screenshot_path = None

    return SemanticMatch(
        event_id=item.id,
        memory_type=item.type,
        score=round(item.similarity, 4),
        final_score=round(item.final_score, 6),
        pinned=item.pinned,
        timestamp=item.timestamp.isoformat(),
        room_name=room_name,
        semantic_text=semantic_text,
        audio_transcript=transcript,
        video_description=video_description,
        transcript_length=len(transcript.strip()),
        screenshot_path=screenshot_path,
    )


def _recall_debug(pack: RecallPack) -> RecallDebug:
    return RecallDebug(
        considered_count=pack.considered_count,
        packed_count=len(pack.included),
        excluded_count=pack.excluded_count,
        memories=[
            RecallDebugMemory(
                id=item.id,
                type=item.type,
                timestamp=item.timestamp.isoformat(),
                similarity=round(item.similarity, 4),
                final_score=round(item.final_score, 6),
                pinned=item.pinned,
            )
            for item in pack.included
        ],
    )


async def _summarize_matches(query: str, matches: list[SemanticMatch]) -> str:
    registry = get_model_registry()
    context = [
        {
            "id": match.event_id,
            "type": match.memory_type,
            "timestamp": match.timestamp,
            "room_name": match.room_name,
            "semantic_text": match.semantic_text,
            "audio_transcript": match.audio_transcript,
        }
        for match in matches
    ]
    prompt = with_monitoring_evidence_context(
        f'User question: "{query}"\n'
        f"Relevant packed memories:\n{json.dumps(context, indent=2)}\n\n"
        "Answer in 2-3 short sentences. Be specific, grounded, and mention uncertainty "
        "if the memories are only a partial match."
    )
    return await invoke_text(
        prompt=prompt,
        system_prompt=with_patient_answer_context(
            "You are a memory assistant for a dementia-support system. Answer only "
            "from the supplied memory events and do not fabricate details. Speak "
            "directly to the patient as 'you' when generic monitoring evidence "
            "describes the patient."
        ),
        model_id=registry.synthesis,
        max_tokens=500,
    )


async def _run_semantic(
    query: str, *, synthesize: bool
) -> SemanticSearchResult:
    settings = get_provider_settings()
    top_k = settings.semantic_search_top_k

    try:
        index_status = await ensure_semantic_index_synced()
        query_embedding = (await embed_texts([query]))[0]
        raw_matches = await _run_blocking(query_similar_embeddings, query_embedding, top_k)
        event_hit_ids = [
            str(match["memory_id"])
            for match in raw_matches
            if match.get("type", "event") != "summary"
        ]
        summary_hit_ids = [
            str(match["memory_id"])
            for match in raw_matches
            if match.get("type") == "summary"
        ]
        matched_events, matched_summaries, pinned_events, active_facts = await asyncio.gather(
            _fetch_events_by_ids(event_hit_ids),
            _fetch_summaries_by_ids(summary_hit_ids),
            _fetch_pinned_events(),
            get_active_facts(),
        )

        payloads: dict[tuple[str, str], Any] = {}
        candidates: dict[tuple[str, str], RecallCandidate] = {}
        raw_by_key = {
            (str(match.get("type", "event")), str(match["memory_id"])): match
            for match in raw_matches
        }
        for event in matched_events:
            key = ("event", event.event_id)
            raw = raw_by_key.get(key)
            similarity = _distance_to_score(float(raw["distance"])) if raw else 0.0
            payloads[key] = event
            candidates[key] = RecallCandidate(
                id=event.event_id,
                type="event",
                text=event.semantic_text,
                timestamp=event.timestamp,
                similarity=similarity,
                importance=event.importance,
                pinned=event.pinned,
            )
        for summary in matched_summaries:
            summary_id = str(summary.get("summary_id"))
            key = ("summary", summary_id)
            raw = raw_by_key.get(key)
            similarity = _distance_to_score(float(raw["distance"])) if raw else 0.0
            payloads[key] = summary
            candidates[key] = RecallCandidate(
                id=summary_id,
                type="summary",
                text=str(summary.get("text", "")),
                timestamp=_summary_timestamp(summary),
                similarity=similarity,
                importance=0.5,
                pinned=False,
            )
        for event in pinned_events:
            key = ("event", event.event_id)
            payloads[key] = event
            candidates.setdefault(
                key,
                RecallCandidate(
                    id=event.event_id,
                    type="event",
                    text=event.semantic_text,
                    timestamp=event.timestamp,
                    similarity=0.0,
                    importance=event.importance,
                    pinned=True,
                ),
            ).pinned = True
        for fact in active_facts:
            if not fact.get("pinned"):
                continue
            fact_id = str(fact.get("fact_id", ""))
            if not fact_id:
                continue
            key = ("fact", fact_id)
            payloads[key] = fact
            candidates[key] = RecallCandidate(
                id=fact_id,
                type="fact",
                text=str(fact.get("text", "")),
                timestamp=normalize_timestamp(
                    fact.get("updated_at") or fact.get("created_at") or now_local()
                ),
                similarity=0.0,
                importance=0.5,
                pinned=True,
            )

        stale_ids = [
            memory_id
            for memory_type, memory_id in raw_by_key
            if (memory_type, memory_id) not in payloads
        ]
        if stale_ids:
            await _run_blocking(delete_event_ids, stale_ids)

        if not candidates:
            return SemanticSearchResult(
                success=False,
                text=(
                    "I couldn't find a closely related memory for that question."
                    if synthesize
                    else ""
                ),
                query=query,
                match_count=0,
                top_k=top_k,
                index_status=index_status,
                error_code="no_semantic_match",
            )

        pack = pack_recall(
            list(candidates.values()),
            token_budget=settings.recall_token_budget,
            half_life_days=settings.recall_half_life_days,
            now=now_local(),
        )
        matches = [
            _match_from_packed(item, payloads[(item.type, item.id)])
            for item in pack.included
        ]
        answer_text = await _summarize_matches(query, matches) if synthesize else ""
        return SemanticSearchResult(
            success=True,
            text=answer_text,
            query=query,
            match_count=len(matches),
            top_k=top_k,
            index_status=index_status,
            matches=matches,
            recall_debug=_recall_debug(pack),
        )
    except Exception as exc:
        logger.exception("Semantic %s failed.", "search" if synthesize else "retrieval")
        return SemanticSearchResult(
            success=False,
            text=(
                "I'm having a little trouble remembering right now. "
                "Please try again in a moment."
            ),
            query=query,
            match_count=0,
            top_k=top_k,
            index_status="error",
            error_code="semantic_query_failed",
            matches=[],
        )


async def run_semantic_retrieval(query: str) -> SemanticSearchResult:
    """Retrieve evidence without spending a second LLM call on synthesis."""
    return await _run_semantic(query, synthesize=False)


async def run_semantic_query(query: str) -> SemanticSearchResult:
    """Smoke-test-only retrieval plus synthesis path.

    Production ``/query`` uses ``run_semantic_retrieval`` and Jeeves' working-
    memory-aware synthesis instead.
    """

    return await _run_semantic(query, synthesize=True)


async def run_semantic_smoke_test(
    query: str = "What was I talking about earlier?",
    force_rebuild: bool = False,
) -> dict[str, Any]:
    rebuild_status = "not_run"
    if force_rebuild:
        rebuild_status = await ensure_semantic_index_synced(force_rebuild=True)
    else:
        rebuild_status = await ensure_semantic_index_synced()

    mongo_event_count = await _count_mongo_events()
    index_count: int | None = None
    index_count_error: str | None = None
    try:
        index_count = await _run_blocking(count_indexed_events)
    except Exception as exc:
        index_count_error = str(exc)

    result = await run_semantic_query(query)
    return {
        "success": result.success,
        "match_count": result.match_count,
        "top_k": result.top_k,
        "text": result.text,
        "index_status": result.index_status,
        "rebuild_status": rebuild_status,
        "mongo_event_count": mongo_event_count,
        "index_count": index_count,
        "index_count_error": index_count_error,
        "embedding": get_embedding_metadata(),
        "event_ids": [match.event_id for match in result.matches],
    }


if __name__ == "__main__":

    async def main():
        print(await run_semantic_smoke_test())
        await close_clients()

    asyncio.run(main())
