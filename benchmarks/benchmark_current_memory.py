"""
benchmark_current_memory.py
============================
Standalone benchmark wrapper around the existing Blue-Dream memory pipeline.
Replaces the local Ollama backend with OpenAI for LLM calls and embeddings,
without modifying any production source files.

This script benchmarks **Time** and **Semantic** query paths by running them
through the production routing, retrieval, and synthesis logic exactly as-is.
It does not generate synthetic data — you must load test data into MongoDB
and ChromaDB yourself (e.g. via a modified consolidator or bulk loader).

Multi-turn conversation context is toggleable via the optional `session_id`
parameter in `run_current_query()`.

Expected environment variables
------------------------------
    OPENAI_API_KEY              Required.
    OPENAI_MODEL                LLM model (default: gpt-4o-mini)
    OPENAI_EMBEDDING_MODEL      Embedding model (default: text-embedding-3-small)
    LLM_EMBEDDING_DIM           Must match OpenAI dims (default: 1536)
    BENCHMARK_CHROMA_DIR        Isolated Chroma directory
    BENCHMARK_MONGO_COLLECTION  Isolated Mongo collection (default: events)
    MONGODB_URI                 MongoDB connection string (default: mongodb://localhost:27017)

Usage
-----
    # 1. Set env vars and load synthetic data into MongoDB + ChromaDB
    # 2. Run sanity check:
    python benchmarks/benchmark_current_memory.py

    # 3. Or import and use programmatically:
    from benchmarks.benchmark_current_memory import run_current_query, close_benchmark_clients
    result = await run_current_query("What was I doing today?", category="time")
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 1. Bootstrap paths and env vars BEFORE any Blue_dream_agents imports
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Use the provider-layer environment surface added by spec 0003.
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_TEXT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
os.environ.setdefault("LLM_SYNTHESIS_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

# Embedding config — the calls are patched below, while registry metadata stays
# aligned with the benchmark model and dimensions.
os.environ.setdefault("EMBEDDING_PROVIDER", "openai")
os.environ.setdefault(
    "LLM_EMBEDDING_MODEL",
    os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
)
os.environ.setdefault("LLM_EMBEDDING_DIM", "1536")

# Isolate the entire Chroma directory so production collections are untouched.
os.environ.setdefault(
    "CHROMA_PERSIST_DIR",
    os.getenv(
        "BENCHMARK_CHROMA_DIR",
        str(project_root / "Storage" / "benchmark-chroma"),
    ),
)

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 2. Monkey-patch db_client to support an alternate Mongo collection
# ---------------------------------------------------------------------------
import Blue_dream_agents.db_client as _db_client

_original_get_events_collection = _db_client.get_events_collection


def _patched_get_events_collection() -> Any:
    """Return the events collection, respecting BENCHMARK_MONGO_COLLECTION."""
    client = _db_client.get_mongo_client()
    db = getattr(client, "dementia_assistance")
    collection_name = os.getenv("BENCHMARK_MONGO_COLLECTION", "events")
    return getattr(db, collection_name)


_db_client.get_events_collection = _patched_get_events_collection


# ---------------------------------------------------------------------------
# 3. Monkey-patch LLM runtime to use OpenAI
# ---------------------------------------------------------------------------
from openai import AsyncOpenAI

_openai_async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_openai_embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

_logger = logging.getLogger(__name__)


async def _openai_invoke_text(
    *,
    prompt: Any,
    system_prompt: str,
    model_id: str,
    tools: Optional[Any] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> str:
    """Drop-in replacement for the provider client's text invocation."""
    if tools:
        _logger.warning("OpenAI benchmark wrapper ignores tools for text invocation.")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": str(prompt)},
    ]
    response = await _openai_async_client.chat.completions.create(
        model=model_id or _openai_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature if temperature is not None else 0.1,
        max_tokens=max_tokens if max_tokens is not None else 1200,
    )
    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RuntimeError("OpenAI returned an empty text response.")
    return content.strip()


async def _openai_invoke_structured(
    *,
    prompt: Any,
    output_model: type[BaseModel],
    system_prompt: str,
    model_id: str,
    tools: Optional[Any] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> BaseModel:
    """Drop-in replacement for the provider client's structured invocation."""
    if tools:
        _logger.warning("OpenAI benchmark wrapper ignores tools for structured invocation.")

    schema = output_model.model_json_schema()
    instruction = (
        "Return only valid JSON. Do not include Markdown, prose, or code fences. "
        "The JSON must validate against this schema:\n"
        f"{json.dumps(schema, indent=2)}"
    )
    if structured_output_prompt:
        instruction += f"\n\nTask-specific output instructions:\n{structured_output_prompt}"

    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{instruction}"},
        {"role": "user", "content": str(prompt)},
    ]
    response = await _openai_async_client.chat.completions.create(
        model=model_id or _openai_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature if temperature is not None else 0.1,
        max_tokens=max_tokens if max_tokens is not None else 1200,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RuntimeError("OpenAI returned an empty structured response.")
    return output_model.model_validate_json(content)


async def _openai_invoke_multimodal_structured(
    *,
    text_prompt: str,
    image_path: str,
    output_model: type[BaseModel],
    system_prompt: str,
    model_id: str,
    fallback_model_id: Optional[str] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs: Any,
) -> BaseModel:
    """Object search is excluded from this benchmark."""
    raise NotImplementedError(
        "Multimodal structured calls are not supported in the benchmark wrapper. "
        "Object search is excluded from the time/semantic benchmark scope."
    )


import Blue_dream_agents.llm.client as _llm_client

_llm_client.invoke_text = _openai_invoke_text
_llm_client.invoke_structured = _openai_invoke_structured
_llm_client.invoke_multimodal_structured = _openai_invoke_multimodal_structured


# ---------------------------------------------------------------------------
# 4. Monkey-patch shared embedding calls to use OpenAI
# ---------------------------------------------------------------------------
async def _openai_embed_texts(
    texts: list[str], task: str = "embedding", **kwargs: Any
) -> list[list[float]]:
    """Drop-in replacement for client.embed_texts using OpenAI."""
    if any(not text.strip() for text in texts):
        raise ValueError("Cannot embed an empty string.")

    response = await _openai_async_client.embeddings.create(
        model=_openai_embedding_model,
        input=texts,
    )
    expected = int(os.getenv("LLM_EMBEDDING_DIM", "1536"))
    embeddings = [list(item.embedding) for item in sorted(response.data, key=lambda x: x.index)]
    for embedding in embeddings:
        if len(embedding) != expected:
            raise ValueError(
                f"Embedding model returned {len(embedding)} dimensions; expected {expected}."
            )
    return embeddings


_llm_client.embed_texts = _openai_embed_texts


# ---------------------------------------------------------------------------
# 5. Import the agent pipeline AFTER all patches are in place
# ---------------------------------------------------------------------------
from Blue_dream_agents.jeeves import run_single_query
from Blue_dream_agents.time_agent import run_time_query
from Blue_dream_agents.semantic_search import run_semantic_retrieval
from Blue_dream_agents.conversation_memory import (
    get_conversation_context,
    append_conversation_turn,
    reset_conversation,
)
from Blue_dream_agents.db_client import close_mongo_client


# ---------------------------------------------------------------------------
# 6. Public API
# ---------------------------------------------------------------------------


async def run_current_query(
    query: str,
    category: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run a single query through the existing Blue-Dream pipeline with an
    OpenAI backend.

    This exercises the full routing + retrieval + synthesis path for Time
    and Semantic queries exactly as the production ``POST /query`` API does.

    Parameters
    ----------
    query : str
        The raw user question.
    category : str
        Documentation/logging hint: ``"time"`` or ``"semantic"``. The actual
        routing is performed by ``jeeves.py`` — this argument is **not**
        used to force a path.
    session_id : str, optional
        If provided, enables multi-turn context. Recent turns are held in
        process memory and the query is rewritten into standalone form before
        routing.

    Returns
    -------
    dict
        A flat result dictionary suitable for logging or downstream analysis::

            {
                "query": str,
                "category": str,
                "session_id": str | None,
                "resolved_query": str,
                "route_intent": str,
                "jeeves_response": {
                    "response_type": str,
                    "text": str,
                    "image_path": str | None,
                    "data": dict | None,
                },
                "isolated_retrieval": dict,
            }

        ``isolated_retrieval`` contains the raw tool output:
        - For ``category="time"``: the ``TimeResult`` from ``time_agent.py``.
        - For ``category="semantic"``: the ``SemanticSearchResult`` from
          ``semantic_search.py`` (matches without synthesis).
    """
    conversation_context = get_conversation_context(session_id)

    # --- Full agentic pipeline (routing + retrieval + synthesis) ---
    jeeves_result = await run_single_query(
        query,
        conversation_context=conversation_context,
    )

    if session_id is not None:
        append_conversation_turn(
            session_id,
            user=query,
            assistant=jeeves_result.text,
            response_type=jeeves_result.response_type,
        )

    # --- Isolated retrieval (raw tool output for inspection) ---
    isolated: dict[str, Any]
    if category == "time":
        time_result = await run_time_query(query)
        isolated = time_result.model_dump(mode="json")
    elif category == "semantic":
        semantic_result = await run_semantic_retrieval(query)
        isolated = semantic_result.model_dump(mode="json")
    else:
        isolated = {
            "note": f"Isolated retrieval not implemented for category '{category}'"
        }

    # Extract routing metadata from the jeeves data payload
    resolved_query = query
    route_intent = "general"
    if jeeves_result.data and isinstance(jeeves_result.data, dict):
        resolved_query = jeeves_result.data.get("resolved_query", query)
        route_intent = jeeves_result.data.get("route_intent", "general")

    return {
        "query": query,
        "category": category,
        "session_id": session_id,
        "resolved_query": resolved_query,
        "route_intent": route_intent,
        "jeeves_response": jeeves_result.model_dump(mode="json"),
        "isolated_retrieval": isolated,
    }


async def reset_session(session_id: str) -> bool:
    """Clear in-process conversation context for a session."""
    return reset_conversation(session_id)


async def close_benchmark_clients() -> None:
    """Close shared MongoDB and OpenAI clients."""
    await close_mongo_client()
    await _openai_async_client.close()


# ---------------------------------------------------------------------------
# 7. CLI sanity-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        print("=" * 60)
        print("Benchmark Current Memory — Quick Sanity Check")
        print("=" * 60)

        # --- Single-turn examples ---
        time_result = await run_current_query(
            "What was I doing today?",
            category="time",
        )
        print("\n[Time Query — Single Turn]")
        print(json.dumps(time_result, indent=2, default=str))

        semantic_result = await run_current_query(
            "Did I mention buying groceries?",
            category="semantic",
        )
        print("\n[Semantic Query — Single Turn]")
        print(json.dumps(semantic_result, indent=2, default=str))

        # --- Multi-turn example (toggleable via session_id) ---
        sid = "benchmark-session-001"

        turn1 = await run_current_query(
            "What was I doing today?",
            category="time",
            session_id=sid,
        )
        print("\n[Multi-turn Turn 1]")
        print(f"Original : {turn1['query']}")
        print(f"Resolved : {turn1['resolved_query']}")
        print(f"Intent   : {turn1['route_intent']}")
        print(f"Response : {turn1['jeeves_response']['text'][:200]}...")

        turn2 = await run_current_query(
            "What room was that in?",
            category="time",
            session_id=sid,
        )
        print("\n[Multi-turn Turn 2]")
        print(f"Original : {turn2['query']}")
        print(f"Resolved : {turn2['resolved_query']}")
        print(f"Intent   : {turn2['route_intent']}")
        print(f"Response : {turn2['jeeves_response']['text'][:200]}...")

        await reset_session(sid)
        await close_benchmark_clients()
        print("\nDone.")

    asyncio.run(_demo())
