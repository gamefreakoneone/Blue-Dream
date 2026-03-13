from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from .llm.settings import get_provider_settings
except ImportError:
    from llm.settings import get_provider_settings

if TYPE_CHECKING:
    try:
        from .memory_schema import MemoryEvent
    except ImportError:
        from memory_schema import MemoryEvent


PRODUCTION_EMBEDDING_DIMENSION = 1024


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
    os.makedirs(normalized_path, exist_ok=True)
    try:
        return chromadb.PersistentClient(path=normalized_path)
    except BaseException as exc:  # pragma: no cover - depends on local Chroma runtime
        raise _wrap_chroma_error("open the persistent client", exc) from None


def clear_cached_clients() -> None:
    _get_cached_persistent_client.cache_clear()


def get_chroma_client(persist_dir: Optional[str] = None):
    settings = get_provider_settings()
    return _get_cached_persistent_client(persist_dir or settings.chroma_persist_dir)


def _get_collection(
    *,
    persist_dir: str,
    collection_name: str,
    metadata: dict[str, Any],
):
    client = get_chroma_client(persist_dir)
    try:
        return client.get_or_create_collection(
            name=collection_name,
            metadata=metadata,
        )
    except BaseException as exc:  # pragma: no cover - depends on local Chroma runtime
        raise _wrap_chroma_error(
            f"open collection '{collection_name}'",
            exc,
        ) from None


def get_event_collection(
    collection_name: Optional[str] = None,
    persist_dir: Optional[str] = None,
):
    settings = get_provider_settings()
    return _get_collection(
        persist_dir=persist_dir or settings.chroma_persist_dir,
        collection_name=collection_name or settings.chroma_collection_name,
        metadata={
            "purpose": "semantic_memory_search",
            "embedding_dimension": PRODUCTION_EMBEDDING_DIMENSION,
        },
    )


def count_indexed_events() -> int:
    return int(get_event_collection().count())


def upsert_event_embedding(event: MemoryEvent, embedding: list[float]) -> None:
    if len(embedding) != PRODUCTION_EMBEDDING_DIMENSION:
        raise ValueError(
            "Semantic embeddings must be "
            f"{PRODUCTION_EMBEDDING_DIMENSION} dimensions, got {len(embedding)}."
        )

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
            }
        ],
    )


def query_similar_embeddings(
    embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    if len(embedding) != PRODUCTION_EMBEDDING_DIMENSION:
        raise ValueError(
            "Semantic query embeddings must be "
            f"{PRODUCTION_EMBEDDING_DIMENSION} dimensions, got {len(embedding)}."
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
    if not event_ids:
        return
    get_event_collection().delete(ids=event_ids)


def inspect_production_index() -> dict[str, Any]:
    settings = get_provider_settings()
    persist_dir = Path(settings.chroma_persist_dir)
    sqlite_path = persist_dir / "chroma.sqlite3"
    state: dict[str, Any] = {
        "persist_dir": str(persist_dir),
        "collection_name": settings.chroma_collection_name,
        "sqlite_exists": sqlite_path.exists(),
        "collection_exists": False,
        "dimension": None,
        "queue_count": 0,
        "smoke_test_count": 0,
        "error": None,
    }
    if not sqlite_path.exists():
        return state

    try:
        connection = sqlite3.connect(str(sqlite_path))
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, dimension FROM collections WHERE name = ? LIMIT 1",
            (settings.chroma_collection_name,),
        )
        row = cursor.fetchone()
        if row:
            state["collection_exists"] = True
            state["collection_id"] = row[0]
            state["dimension"] = row[1]

        cursor.execute("SELECT COUNT(*) FROM embeddings_queue")
        state["queue_count"] = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM embeddings_queue WHERE id = ?",
            ("semantic-smoke-test",),
        )
        state["smoke_test_count"] = int(cursor.fetchone()[0])
    except sqlite3.Error as exc:
        state["error"] = str(exc)
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass

    return state


def reset_production_index() -> str:
    settings = get_provider_settings()
    persist_dir = Path(settings.chroma_persist_dir)
    clear_cached_clients()
    if persist_dir.exists():
        shutil.rmtree(persist_dir, ignore_errors=True)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return str(persist_dir)


def run_vector_store_smoke_test() -> dict[str, Any]:
    test_id = "semantic-smoke-test"
    first_embedding = [0.001] * PRODUCTION_EMBEDDING_DIMENSION
    second_embedding = [0.001] * PRODUCTION_EMBEDDING_DIMENSION

    with tempfile.TemporaryDirectory(prefix="blue-dream-chroma-smoke-") as temp_dir:
        collection = _get_collection(
            persist_dir=temp_dir,
            collection_name="semantic_smoke_test",
            metadata={
                "purpose": "semantic_memory_smoke_test",
                "embedding_dimension": PRODUCTION_EMBEDDING_DIMENSION,
            },
        )
        collection.upsert(
            ids=[test_id],
            embeddings=[first_embedding],
            metadatas=[{"purpose": "smoke_test"}],
        )
        results = collection.query(query_embeddings=[second_embedding], n_results=1)
        ids = results.get("ids", [[]])[0]
        return {
            "top_match": ids[0] if ids else None,
            "match_count": len(ids),
            "persist_dir": temp_dir,
        }


if __name__ == "__main__":
    print(run_vector_store_smoke_test())
