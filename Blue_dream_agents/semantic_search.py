from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

try:
    from .llm.embedding_client import embed_text
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from .llm.settings import get_provider_settings
    from .llm.strands_runtime import invoke_text
    from .memory_schema import MemoryEvent, memory_event_from_mongo
    from .vector_store import (
        count_indexed_events,
        delete_event_ids,
        get_embedding_dimension,
        get_embedding_metadata,
        inspect_production_index,
        query_similar_embeddings,
        reset_production_index,
        upsert_event_embedding,
    )
except ImportError:
    from llm.embedding_client import embed_text
    from llm.model_registry import get_model_registry
    from llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from llm.settings import get_provider_settings
    from llm.strands_runtime import invoke_text
    from memory_schema import MemoryEvent, memory_event_from_mongo
    from vector_store import (
        count_indexed_events,
        delete_event_ids,
        get_embedding_dimension,
        get_embedding_metadata,
        inspect_production_index,
        query_similar_embeddings,
        reset_production_index,
        upsert_event_embedding,
    )


logger = logging.getLogger(__name__)


class SemanticMatch(BaseModel):
    event_id: str
    score: float
    timestamp: str
    room_name: str
    semantic_text: str
    audio_transcript: str = ""
    video_description: str = ""
    transcript_length: int = 0
    screenshot_path: Optional[str] = None


class SemanticSearchResult(BaseModel):
    success: bool
    text: str
    query: str
    match_count: int
    top_k: int
    index_status: str = "ready"
    error_code: Optional[str] = None
    matches: List[SemanticMatch] = Field(default_factory=list)


_mongo_client: Optional[AsyncIOMotorClient] = None
_sync_lock = asyncio.Lock()
_index_bootstrapped = False


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(get_provider_settings().mongodb_uri)
    return _mongo_client


async def close_clients():
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


async def index_memory_event(event: MemoryEvent) -> None:
    embedding = await _run_blocking(
        embed_text,
        event.semantic_text,
        "document",
        get_embedding_dimension(),
    )
    await _run_blocking(upsert_event_embedding, event, embedding)


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
        events_by_id[event.event_id] = event

    return [events_by_id[event_id] for event_id in event_ids if event_id in events_by_id]


async def _count_mongo_events() -> int:
    collection = get_mongo_client().dementia_assistance.events
    return int(await collection.count_documents({}))


async def _index_all_mongo_events() -> bool:
    collection = get_mongo_client().dementia_assistance.events
    indexed_any = False
    async for doc in collection.find().sort("timestamp", 1):
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
    return indexed_any


def _index_requires_reset(index_state: dict[str, Any]) -> bool:
    if index_state.get("error"):
        return True

    dimension = index_state.get("dimension")
    expected_metadata = get_embedding_metadata()
    if dimension not in (None, expected_metadata["embedding_dimension"]):
        return True

    metadata = index_state.get("metadata") or {}
    if index_state.get("collection_exists"):
        for key, expected_value in expected_metadata.items():
            if metadata.get(key) != expected_value:
                return True

    return bool(index_state.get("smoke_test_count"))


async def ensure_semantic_index_synced(force_rebuild: bool = False) -> str:
    global _index_bootstrapped
    async with _sync_lock:
        index_status = "ready"
        index_state = await _run_blocking(inspect_production_index)
        if force_rebuild or _index_requires_reset(index_state):
            reset_reason = (
                "manual rebuild"
                if force_rebuild
                else f"invalid persisted index state: {index_state}"
            )
            logger.warning("Resetting semantic index due to %s.", reset_reason)
            await _run_blocking(reset_production_index)
            _index_bootstrapped = False
            index_status = "reset"

        try:
            indexed_count = await _run_blocking(count_indexed_events)
        except Exception as exc:
            logger.warning("Semantic index health check failed, resetting index: %s", exc)
            await _run_blocking(reset_production_index)
            indexed_count = 0
            index_status = "reset"

        mongo_count = await _count_mongo_events()
        if indexed_count > 0:
            if mongo_count and indexed_count < mongo_count:
                logger.info(
                    "Semantic index has %s events but Mongo has %s; syncing missing events.",
                    indexed_count,
                    mongo_count,
                )
                indexed_any = await _index_all_mongo_events()
                _index_bootstrapped = True
                if indexed_any:
                    return "synced" if index_status == "ready" else "recovered"
            _index_bootstrapped = True
            return "ready" if index_status == "ready" else "recovered"

        indexed_any = await _index_all_mongo_events()

        _index_bootstrapped = True
        if indexed_any:
            return "bootstrapped" if index_status == "ready" else "rebuilt"
        return "empty"


def _distance_to_score(distance: float) -> float:
    return round(1.0 / (1.0 + max(distance, 0.0)), 4)


def _match_from_event(event: MemoryEvent, distance: float) -> SemanticMatch:
    transcript = event.audio_transcript or ""
    return SemanticMatch(
        event_id=event.event_id,
        score=_distance_to_score(distance),
        timestamp=event.timestamp.isoformat(),
        room_name=event.room_name,
        semantic_text=event.semantic_text,
        audio_transcript=transcript,
        video_description=event.video_description,
        transcript_length=len(transcript.strip()),
        screenshot_path=event.screenshot_path or None,
    )


async def _summarize_matches(query: str, events: list[MemoryEvent]) -> str:
    registry = get_model_registry()
    context = [
        {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "room_name": event.room_name,
            "semantic_text": event.semantic_text,
            "audio_transcript": event.audio_transcript,
        }
        for event in events
    ]
    prompt = with_monitoring_evidence_context(
        f'User question: "{query}"\n'
        f"Relevant memory events:\n{json.dumps(context, indent=2)}\n\n"
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


async def run_semantic_query(query: str) -> SemanticSearchResult:
    settings = get_provider_settings()
    top_k = settings.semantic_search_top_k

    try:
        index_status = await ensure_semantic_index_synced()
        query_embedding = await _run_blocking(
            embed_text,
            query,
            "query",
            get_embedding_dimension(),
        )
        raw_matches = await _run_blocking(query_similar_embeddings, query_embedding, top_k)
        if not raw_matches:
            return SemanticSearchResult(
                success=False,
                text="I couldn't find a closely related memory for that question.",
                query=query,
                match_count=0,
                top_k=top_k,
                index_status=index_status,
                error_code="no_semantic_match",
                matches=[],
            )

        matched_ids = [match["event_id"] for match in raw_matches]
        matched_events = await _fetch_events_by_ids(matched_ids)
        if not matched_events:
            await _run_blocking(delete_event_ids, matched_ids)
            return SemanticSearchResult(
                success=False,
                text="I found semantic matches, but I couldn't recover the full records.",
                query=query,
                match_count=0,
                top_k=top_k,
                index_status=index_status,
                error_code="stale_vector_matches",
                matches=[],
            )

        events_by_id = {event.event_id: event for event in matched_events}
        stale_ids = [event_id for event_id in matched_ids if event_id not in events_by_id]
        if stale_ids:
            await _run_blocking(delete_event_ids, stale_ids)

        ordered_events = [
            events_by_id[event_id] for event_id in matched_ids if event_id in events_by_id
        ]
        answer_text = await _summarize_matches(query, ordered_events)
        raw_matches_by_id = {
            raw_match["event_id"]: raw_match for raw_match in raw_matches
        }
        matches = [
            _match_from_event(event, raw_matches_by_id[event.event_id]["distance"])
            for event in ordered_events
        ]
        return SemanticSearchResult(
            success=True,
            text=answer_text,
            query=query,
            match_count=len(matches),
            top_k=top_k,
            index_status=index_status,
            matches=matches,
        )
    except Exception as exc:
        logger.exception("Semantic search failed.")
        return SemanticSearchResult(
            success=False,
            text=f"I'm sorry, I had trouble searching your memories: {exc}",
            query=query,
            match_count=0,
            top_k=top_k,
            index_status="error",
            error_code="semantic_query_failed",
            matches=[],
        )


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
