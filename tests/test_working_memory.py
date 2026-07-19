import asyncio

from Blue_dream_agents.memory_schema import MemoryEvent
from Blue_dream_agents.timezone_utils import now_local


def _event() -> MemoryEvent:
    return MemoryEvent(
        event_id="working-memory-event",
        timestamp=now_local(),
        room_number=1,
        room_name="Living Room",
        semantic_text="Your keys were placed on the table.",
        video_description="Your keys were placed on the table.",
    )


def test_object_answer_prompt_includes_working_memory(monkeypatch):
    from Blue_dream_agents import object_detector

    captured = {}

    async def structured(**kwargs):
        captured.update(kwargs)
        return object_detector.ObjectLastKnownResult(
            found=True,
            room_name="Living Room",
            anchor_event_id="working-memory-event",
            summary="Your keys were last seen on the table.",
            confidence="high",
        )

    monkeypatch.setattr(object_detector, "invoke_structured", structured)
    result = asyncio.run(
        object_detector._analyze_last_known_location(
            "keys",
            [_event()],
            "What you know about the patient:\n- Prefers the blue keychain\n\n"
            "Today's active reminders:\n- Reminder: Take medicine",
        )
    )

    assert result.found is True
    assert "Prefers the blue keychain" in captured["system_prompt"]
    assert "Take medicine" in captured["system_prompt"]


def test_time_answer_prompt_includes_working_memory(monkeypatch):
    from Blue_dream_agents import time_agent

    captured = {}

    async def text(**kwargs):
        captured.update(kwargs)
        return "You put your keys on the table."

    monkeypatch.setattr(time_agent, "invoke_text", text)
    result = asyncio.run(
        time_agent._summarize_with_llm(
            [_event()],
            "What happened today?",
            "What you know about the patient:\n- Prefers the blue keychain\n\n"
            "Today's active reminders:\n- Reminder: Take medicine",
        )
    )

    assert result == "You put your keys on the table."
    assert "Prefers the blue keychain" in captured["system_prompt"]
    assert "Take medicine" in captured["system_prompt"]
