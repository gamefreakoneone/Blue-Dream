from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from .llm.model_registry import resolve
    from .llm.settings import get_provider_settings
except ImportError:
    from llm.model_registry import resolve
    from llm.settings import get_provider_settings

if TYPE_CHECKING:
    try:
        from .memory_schema import MemoryEvent
    except ImportError:
        from memory_schema import MemoryEvent


logger = logging.getLogger(__name__)


def _ensure_chroma_available() -> None:
    if chromadb is None:
        raise RuntimeError(
            "ChromaDB is not installed. Add `chromadb` to the environment before "
            "using semantic search."
        )


def _normalize_path(path: str) -> str:
    return str(Path(path).resolve())


def _wrap_chroma_error(action: str, exc: BaseException) -> RuntimeError:
    return RuntimeError(f"ChromaDB failed while trying to {action}: {exc}")


@lru_cache(maxsize=4)
def _get_cached_persistent_client(persist_dir: str):
    _ensure_chroma_available()
    normalized_path = _normalize_path(persist_dir)
    Path(normalized_path).mkdir(parents=True, exist_ok=True)
    try:
        return chromadb.PersistentClient(path=normalized_path)
    except BaseException as exc:  # pragma: no cover - local Chroma runtime
        raise _wrap_chroma_error("open the persistent client", exc) from None


def clear_cached_clients() -> None:
    _get_cached_persistent_client.cache_clear()


def get_chroma_client(persist_dir: Optional[str] = None):
    settings = get_provider_settings()
    return _get_cached_persistent_client(persist_dir or settings.chroma_persist_dir)


def _model_slug(model: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "_", model.strip().lower()).strip("_-")
    return slug or "unknown"


def get_event_collection_name() -> str:
    target = resolve("embedding")
    if target.embedding_dim is None:
        raise RuntimeError("The embedding target did not declare a vector dimension.")
    return (
        f"memory_events__{target.provider}__{_model_slug(target.model)}__"
        f"{target.embedding_dim}"
    )


def get_embedding_dimension() -> int:
    dimension = resolve("embedding").embedding_dim
    if dimension is None:
        raise RuntimeError("The embedding target did not declare a vector dimension.")
    return dimension


def get_embedding_metadata() -> dict[str, Any]:
    target = resolve("embedding")
    return {
        "provider": target.provider,
        "model": target.model,
        "dim": get_embedding_dimension(),
    }


def _metadata_matches(actual: Optional[dict[str, Any]]) -> bool:
    metadata = actual or {}
    return all(metadata.get(key) == value for key, value in get_embedding_metadata().items())


def _create_event_collection(*, persist_dir: str):
    client = get_chroma_client(persist_dir)
    collection_name = get_event_collection_name()
    metadata = {
        "purpose": "semantic_memory_search",
        **get_embedding_metadata(),
    }
    try:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata=metadata,
        )
        if not _metadata_matches(collection.metadata):
            logger.warning(
                "Recreating active Chroma collection %s due to metadata mismatch.",
                collection_name,
            )
            client.delete_collection(collection_name)
            collection = client.create_collection(
                name=collection_name,
                metadata=metadata,
            )
        return collection
    except BaseException as exc:  # pragma: no cover - local Chroma runtime
        raise _wrap_chroma_error(
            f"open collection '{collection_name}'", exc
        ) from None


def get_event_collection(persist_dir: Optional[str] = None):
    settings = get_provider_settings()
    return _create_event_collection(
        persist_dir=persist_dir or settings.chroma_persist_dir
    )


def reset_active_event_collection(persist_dir: Optional[str] = None):
    settings = get_provider_settings()
    resolved_dir = persist_dir or settings.chroma_persist_dir
    client = get_chroma_client(resolved_dir)
    collection_name = get_event_collection_name()
    try:
        try:
            client.delete_collection(collection_name)
        except Exception as exc:
            if "does not exist" not in str(exc).lower() and "not found" not in str(exc).lower():
                raise
        return _create_event_collection(persist_dir=resolved_dir)
    except BaseException as exc:  # pragma: no cover - local Chroma runtime
        raise _wrap_chroma_error(
            f"recreate active collection '{collection_name}'", exc
        ) from None


def count_indexed_events() -> int:
    return int(get_event_collection().count())


def upsert_event_embedding(event: MemoryEvent, embedding: list[float]) -> None:
    expected_dimension = get_embedding_dimension()
    if len(embedding) != expected_dimension:
        raise ValueError(
            "Semantic embeddings must be "
            f"{expected_dimension} dimensions, got {len(embedding)}."
        )

    embedding_metadata = get_embedding_metadata()
    get_event_collection().upsert(
        ids=[event.event_id],
        embeddings=[embedding],
        metadatas=[
            {
                "event_id": event.event_id,
                "room_number": event.room_number,
                "room_name": event.room_name,
                "timestamp": event.timestamp.isoformat(),
                "has_screenshot": bool(event.screenshot_path),
                **embedding_metadata,
            }
        ],
    )


def query_similar_embeddings(
    embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    expected_dimension = get_embedding_dimension()
    if len(embedding) != expected_dimension:
        raise ValueError(
            "Semantic query embeddings must be "
            f"{expected_dimension} dimensions, got {len(embedding)}."
        )

    results = get_event_collection().query(
        query_embeddings=[embedding],
        n_results=top_k,
    )
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    matches: list[dict[str, Any]] = []
    for index, event_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = float(distances[index]) if index < len(distances) else 0.0
        matches.append(
            {
                "event_id": event_id,
                "distance": distance,
                "metadata": metadata or {},
            }
        )
    return matches


def delete_event_ids(event_ids: list[str]) -> None:
    if event_ids:
        get_event_collection().delete(ids=event_ids)


def list_indexed_event_ids() -> list[str]:
    results = get_event_collection().get(include=[])
    return [str(event_id) for event_id in results.get("ids", [])]


def run_vector_store_smoke_test() -> dict[str, Any]:
    _ensure_chroma_available()
    test_id = "semantic-smoke-test"
    embedding_dimension = get_embedding_dimension()
    embedding = [0.001] * embedding_dimension
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name="semantic_smoke_test",
        metadata={
            "purpose": "semantic_memory_smoke_test",
            **get_embedding_metadata(),
        },
    )
    collection.upsert(
        ids=[test_id],
        embeddings=[embedding],
        metadatas=[{"purpose": "smoke_test"}],
    )
    results = collection.query(query_embeddings=[embedding], n_results=1)
    ids = results.get("ids", [[]])[0]
    return {
        "top_match": ids[0] if ids else None,
        "match_count": len(ids),
        "embedding_dimension": embedding_dimension,
        "persist_dir": None,
    }


if __name__ == "__main__":
    print(run_vector_store_smoke_test())
