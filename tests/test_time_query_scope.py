import asyncio
import datetime as dt
from types import SimpleNamespace

from Blue_dream_agents import jeeves, time_agent
from Blue_dream_agents.memory_schema import MemoryEvent
from Blue_dream_agents.semantic_search import SemanticSearchResult
from Blue_dream_agents.timezone_utils import LOCAL_TZ


NOW = dt.datetime(2026, 7, 20, 8, 31, tzinfo=LOCAL_TZ)


def _run(awaitable):
    return asyncio.run(awaitable)


def _event(
    event_id: str,
    timestamp: dt.datetime,
    *,
    activity: str,
    speech: str = "",
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id,
        timestamp=timestamp,
        room_number=1,
        room_name="Living Room",
        semantic_text=" ".join(part for part in (activity, speech) if part),
        video_description=activity,
        audio_transcript=speech,
    )


def test_day_part_filters_use_calendar_day_boundaries(monkeypatch):
    monkeypatch.setattr(time_agent, "now_local", lambda: NOW)

    morning_start, morning_end, morning_desc = time_agent._build_time_filter(
        "yesterday", "morning"
    )
    evening_start, evening_end, evening_desc = time_agent._build_time_filter(
        "yesterday evening"
    )
    full_start, full_end, full_desc = time_agent._build_time_filter(
        "yesterday", "all_day"
    )

    assert morning_start == dt.datetime(2026, 7, 19, 6, tzinfo=LOCAL_TZ)
    assert morning_end == dt.datetime(
        2026, 7, 19, 11, 59, 59, 999999, tzinfo=LOCAL_TZ
    )
    assert morning_desc == "yesterday morning"
    assert evening_start == dt.datetime(2026, 7, 19, 17, tzinfo=LOCAL_TZ)
    assert evening_end == dt.datetime.max.replace(
        year=2026, month=7, day=19, tzinfo=LOCAL_TZ
    )
    assert evening_desc == "yesterday evening"
    assert full_start == dt.datetime(2026, 7, 19, tzinfo=LOCAL_TZ)
    assert full_end == dt.datetime.max.replace(
        year=2026, month=7, day=19, tzinfo=LOCAL_TZ
    )
    assert full_desc == "yesterday"


def test_explicit_day_part_overrides_broader_llm_plan(monkeypatch):
    async def structured(**kwargs):
        return time_agent.TimeQueryPlan(
            intent="timeline",
            time_range="yesterday",
            day_part="all_day",
        )

    monkeypatch.setattr(time_agent, "invoke_structured", structured)
    plan = _run(time_agent._plan_time_query("What did I do yesterday morning?"))

    assert plan.intent == "timeline"
    assert plan.time_range == "yesterday"
    assert plan.day_part == "morning"


def test_deterministic_transcript_plan_preserves_evening_scope(monkeypatch):
    async def unexpected_structured(**kwargs):
        raise AssertionError("speech recall should use the deterministic plan")

    monkeypatch.setattr(time_agent, "invoke_structured", unexpected_structured)
    plan = _run(
        time_agent._plan_time_query(
            "What did I talk to my dad about yesterday evening?"
        )
    )

    assert plan.intent == "transcripts"
    assert plan.time_range == "yesterday"
    assert plan.day_part == "evening"


def test_morning_timeline_excludes_evening_events_and_keeps_exact_question(
    monkeypatch,
):
    monkeypatch.setattr(time_agent, "now_local", lambda: NOW)
    events = [
        _event(
            "breakfast",
            dt.datetime(2026, 7, 19, 9, tzinfo=LOCAL_TZ),
            activity="The person ate breakfast.",
        ),
        _event(
            "dad-call",
            dt.datetime(2026, 7, 19, 20, tzinfo=LOCAL_TZ),
            activity="The person called Dad and later made curry.",
        ),
    ]
    captured = {}

    async def get_events(start_dt, end_dt, room_number=None, limit=100):
        captured["start"] = start_dt
        captured["end"] = end_dt
        return [event for event in events if start_dt <= event.timestamp <= end_dt]

    async def text(**kwargs):
        captured.update(kwargs)
        return "You ate breakfast in the living room."

    monkeypatch.setattr(time_agent, "_get_events", get_events)
    monkeypatch.setattr(time_agent, "invoke_text", text)
    monkeypatch.setattr(
        time_agent,
        "get_model_registry",
        lambda: SimpleNamespace(synthesis="test-model"),
    )

    result = _run(
        time_agent.get_activity_history(
            "yesterday",
            day_part="morning",
            user_query="What did I do yesterday morning?",
        )
    )

    assert result.event_count == 1
    assert captured["start"].hour == 6
    assert captured["end"].hour == 11
    assert 'Question: "What did I do yesterday morning?"' in captured["prompt"]
    assert "called Dad" not in captured["prompt"]
    assert "do not turn a focused question into a whole-day recap" in captured[
        "prompt"
    ]


def test_specific_transcript_prompt_keeps_question_and_rejects_later_topics(
    monkeypatch,
):
    monkeypatch.setattr(time_agent, "now_local", lambda: NOW)
    captured = {}
    events = [
        _event(
            "dad-call",
            dt.datetime(2026, 7, 19, 20, tzinfo=LOCAL_TZ),
            activity="The person was on a phone call.",
            speech="Dad, I will be home soon and bring gummy bears for the kids.",
        ),
        _event(
            "dinner",
            dt.datetime(2026, 7, 19, 20, 30, tzinfo=LOCAL_TZ),
            activity="The person ordered dinner.",
            speech="I will use the curry special offer.",
        ),
    ]

    async def get_events(start_dt, end_dt, room_number=None, limit=100):
        captured["start"] = start_dt
        captured["end"] = end_dt
        return [event for event in events if start_dt <= event.timestamp <= end_dt]

    async def text(**kwargs):
        captured.update(kwargs)
        return "You told your dad you would be home soon and bring gummy bears."

    monkeypatch.setattr(time_agent, "_get_events", get_events)
    monkeypatch.setattr(time_agent, "invoke_text", text)
    monkeypatch.setattr(
        time_agent,
        "get_model_registry",
        lambda: SimpleNamespace(synthesis="test-model"),
    )

    result = _run(
        time_agent.get_recent_transcripts(
            "yesterday",
            day_part="evening",
            user_query="What did I talk to my dad about yesterday evening?",
        )
    )

    assert result.transcript_count == 2
    assert captured["start"].hour == 17
    assert 'Question: "What did I talk to my dad about yesterday evening?"' in captured[
        "prompt"
    ]
    assert "Answer the exact question, not every topic" in captured["prompt"]
    assert "Do not mention what happened before or after" in captured["prompt"]
    assert result.summary == (
        "You told your dad you would be home soon and bring gummy bears."
    )


def test_full_day_timeline_still_receives_all_day_events(monkeypatch):
    monkeypatch.setattr(time_agent, "now_local", lambda: NOW)
    events = [
        _event(
            "morning",
            dt.datetime(2026, 7, 19, 9, tzinfo=LOCAL_TZ),
            activity="The person ate breakfast.",
        ),
        _event(
            "evening",
            dt.datetime(2026, 7, 19, 20, tzinfo=LOCAL_TZ),
            activity="The person called Dad.",
        ),
    ]

    async def get_events(start_dt, end_dt, room_number=None, limit=100):
        return [event for event in events if start_dt <= event.timestamp <= end_dt]

    async def text(**kwargs):
        return "You ate breakfast and later called your dad."

    monkeypatch.setattr(time_agent, "_get_events", get_events)
    monkeypatch.setattr(time_agent, "invoke_text", text)
    monkeypatch.setattr(
        time_agent,
        "get_model_registry",
        lambda: SimpleNamespace(synthesis="test-model"),
    )

    result = _run(
        time_agent.get_activity_history(
            "yesterday",
            day_part="all_day",
            user_query="What did I do yesterday?",
        )
    )

    assert result.event_count == 2
    assert result.summary == "You ate breakfast and later called your dad."


def test_semantic_synthesis_uses_exact_scope_instruction(monkeypatch):
    captured = {}

    async def text(**kwargs):
        captured.update(kwargs)
        return "You discussed gummy bears with your dad."

    monkeypatch.setattr(jeeves, "invoke_text", text)
    monkeypatch.setattr(
        jeeves,
        "get_model_registry",
        lambda: SimpleNamespace(synthesis="test-model"),
    )
    result = SemanticSearchResult(
        success=False,
        text="",
        query="What did I discuss with Dad?",
        match_count=0,
        top_k=5,
        matches=[],
    )

    answer = _run(
        jeeves._synthesize_semantic_answer(
            result.query,
            result,
            working_memory_block="",
        )
    )

    assert answer == "You discussed gummy bears with your dad."
    assert "Do not volunteer neighboring events" in captured["system_prompt"]
    assert "unless the user explicitly asks for a full chronology" in captured[
        "system_prompt"
    ]
