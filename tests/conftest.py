import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:1")
os.environ.setdefault("LOCAL_LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:1")
os.environ.setdefault("CHROMA_PERSIST_DIR", str(ROOT / "Storage" / "test-chroma"))


@pytest.fixture
def api_module():
    from Blue_dream_agents import api

    return api


@pytest.fixture
def client(monkeypatch, api_module):
    from Blue_dream_agents.jeeves import JeevesResponse

    async def noop():
        return None

    async def canned_query(query, conversation_context=None):
        return JeevesResponse(
            response_type="general",
            text=f"Remembered: {query}",
            image_path=None,
            data=None,
        )

    monkeypatch.setattr(api_module, "ensure_events_indexes", noop)
    monkeypatch.setattr(api_module, "initialize_alert_indexes", noop)
    monkeypatch.setattr(api_module, "close_http_client", noop)
    monkeypatch.setattr(api_module, "close_mongo_client", noop)
    monkeypatch.setattr(api_module, "run_single_query", canned_query)

    with TestClient(api_module.app) as test_client:
        yield test_client
