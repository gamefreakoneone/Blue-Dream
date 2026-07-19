import asyncio

import pytest

from scripts import spec0007_rehearsal


def test_rehearsal_refuses_production_like_stores_before_client_call(monkeypatch):
    client_called = False

    def forbidden_client():
        nonlocal client_called
        client_called = True
        raise AssertionError("Mongo client must not be created")

    monkeypatch.setenv("SPEC0007_REHEARSAL_ALLOW_DESTRUCTIVE", "1")
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv(
        "CHROMA_PERSIST_DIR",
        str(spec0007_rehearsal.ROOT / "Storage" / "chroma"),
    )
    monkeypatch.setattr(spec0007_rehearsal, "get_mongo_client", forbidden_client)

    with pytest.raises(RuntimeError, match="Refusing to run the destructive"):
        asyncio.run(spec0007_rehearsal.main("seed"))

    assert client_called is False
