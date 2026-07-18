from fastapi.testclient import TestClient


PATIENT_SAFE_MESSAGE = (
    "I'm having a little trouble remembering right now. "
    "Please try again in a moment."
)


def test_legacy_query_body_returns_jeeves_contract(client):
    response = client.post("/query", json={"query": "Where are my keys?"})

    assert response.status_code == 200
    assert set(response.json()) == {"response_type", "text", "image_path", "data"}


def test_query_accepts_session_id(client):
    response = client.post(
        "/query",
        json={"query": "What happened?", "session_id": "session-1"},
    )

    assert response.status_code == 200
    assert response.json()["response_type"] == "general"


def test_conversation_reset_contract(client):
    response = client.post(
        "/conversation/reset",
        json={"session_id": "session-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_internal_jeeves_failure_returns_safe_http_200(
    client,
    monkeypatch,
    api_module,
):
    from Blue_dream_agents import jeeves

    async def fail_resolution(query, conversation_context):
        raise RuntimeError("SENTINEL_QUERY_SECRET")

    monkeypatch.setattr(jeeves, "_resolve_query_with_context", fail_resolution)
    monkeypatch.setattr(api_module, "run_single_query", jeeves.run_single_query)

    response = client.post("/query", json={"query": "Please remember"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"response_type", "text", "image_path", "data"}
    assert payload["text"] == PATIENT_SAFE_MESSAGE
    assert "SENTINEL_QUERY_SECRET" not in payload["text"]
    assert "RuntimeError" not in payload["text"]


def test_api_wrapper_failure_keeps_status_and_hides_detail(
    client,
    monkeypatch,
    api_module,
):
    async def fail_query(query, conversation_context=None):
        raise RuntimeError("SENTINEL_API_SECRET")

    monkeypatch.setattr(api_module, "run_single_query", fail_query)

    response = client.post("/query", json={"query": "Please remember"})

    assert response.status_code == 500
    assert response.json() == {"detail": api_module.GENERIC_ERROR_DETAIL}
    assert "SENTINEL_API_SECRET" not in response.text


def test_lifespan_initializes_and_closes_clients(monkeypatch, api_module):
    calls = []

    async def record(name):
        calls.append(name)

    monkeypatch.setattr(
        api_module,
        "ensure_events_indexes",
        lambda: record("events"),
    )
    monkeypatch.setattr(
        api_module,
        "initialize_alert_indexes",
        lambda: record("alerts"),
    )
    monkeypatch.setattr(
        api_module,
        "close_llm_clients",
        lambda: record("llm-close"),
    )
    monkeypatch.setattr(
        api_module,
        "close_mongo_client",
        lambda: record("mongo-close"),
    )

    with TestClient(api_module.app):
        pass

    assert calls == ["events", "alerts", "llm-close", "mongo-close"]


def test_lifespan_tolerates_index_failure(monkeypatch, api_module):
    calls = []

    async def fail_indexes():
        raise RuntimeError("Mongo unavailable")

    async def record_close(name):
        calls.append(name)

    monkeypatch.setattr(api_module, "ensure_events_indexes", fail_indexes)
    monkeypatch.setattr(
        api_module,
        "close_llm_clients",
        lambda: record_close("llm-close"),
    )
    monkeypatch.setattr(
        api_module,
        "close_mongo_client",
        lambda: record_close("mongo-close"),
    )

    with TestClient(api_module.app):
        pass

    assert calls == ["llm-close", "mongo-close"]
