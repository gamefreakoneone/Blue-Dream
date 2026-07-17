import asyncio
from types import SimpleNamespace

import pytest


PATIENT_SAFE_MESSAGE = (
    "I'm having a little trouble remembering right now. "
    "Please try again in a moment."
)
SENTINEL = "SENTINEL_PATIENT_SECRET"


async def raise_sentinel(*args, **kwargs):
    raise RuntimeError(SENTINEL)


def assert_safe_text(text):
    assert text == PATIENT_SAFE_MESSAGE
    assert SENTINEL not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text


def test_jeeves_exception_path_is_safe(monkeypatch, caplog):
    from Blue_dream_agents import jeeves

    monkeypatch.setattr(jeeves, "_resolve_query_with_context", raise_sentinel)

    with caplog.at_level("ERROR"):
        result = asyncio.run(jeeves.run_single_query("help me remember"))

    assert_safe_text(result.text)
    assert SENTINEL in caplog.text


@pytest.mark.parametrize(
    "function_name",
    ["run_semantic_retrieval", "run_semantic_query"],
)
def test_semantic_exception_paths_are_safe(monkeypatch, function_name):
    from Blue_dream_agents import semantic_search

    monkeypatch.setattr(
        semantic_search,
        "ensure_semantic_index_synced",
        raise_sentinel,
    )

    result = asyncio.run(getattr(semantic_search, function_name)("memory"))

    assert_safe_text(result.text)


@pytest.mark.parametrize(
    ("function_name", "args", "kwargs", "text_attribute"),
    [
        (
            "get_time_window_context",
            ("2026-07-17T12:00:00-07:00",),
            {"query": "what happened"},
            "summary",
        ),
        ("get_activity_history", ("today",), {}, "summary"),
        ("get_room_activity", ("Bedroom",), {}, "summary"),
        ("get_recent_transcripts", (), {}, "summary"),
        ("check_activity", ("made tea",), {}, "summary"),
    ],
)
def test_time_lookup_exception_paths_are_safe(
    monkeypatch,
    function_name,
    args,
    kwargs,
    text_attribute,
):
    from Blue_dream_agents import time_agent

    monkeypatch.setattr(time_agent, "_get_events", raise_sentinel)

    result = asyncio.run(getattr(time_agent, function_name)(*args, **kwargs))

    assert_safe_text(getattr(result, text_attribute))


def test_time_query_exception_path_is_safe(monkeypatch):
    from Blue_dream_agents import time_agent

    monkeypatch.setattr(time_agent, "_plan_time_query", raise_sentinel)

    result = asyncio.run(time_agent.run_time_query("what happened"))

    assert_safe_text(result.text)


def test_object_search_exception_path_is_safe(monkeypatch):
    from Blue_dream_agents import object_detector

    async def parsed_query(*args, **kwargs):
        return SimpleNamespace(object_name="keys", room_id=None)

    monkeypatch.setattr(
        object_detector,
        "_get_latest_room_states",
        raise_sentinel,
    )
    monkeypatch.setattr(object_detector, "_parse_query_intent", parsed_query)

    result = asyncio.run(object_detector.search_for_object("where are my keys"))

    assert_safe_text(result.description)
