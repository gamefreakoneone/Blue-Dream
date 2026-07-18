import asyncio
import importlib
from types import SimpleNamespace

import pytest


def test_alert_indexes_initialize_once_and_retry(monkeypatch):
    from Blue_dream_agents import alert_service

    calls = 0

    async def create_indexes():
        nonlocal calls
        calls += 1

    alert_service._alert_indexes_ready = False
    alert_service._alert_indexes_lock = asyncio.Lock()
    monkeypatch.setattr(alert_service, "ensure_alert_indexes_in_db", create_indexes)

    async def initialize_concurrently():
        await asyncio.gather(
            *(alert_service.initialize_alert_indexes() for _ in range(5))
        )

    asyncio.run(initialize_concurrently())
    assert calls == 1

    attempts = 0

    async def fail_once():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary Mongo failure")

    alert_service._alert_indexes_ready = False
    alert_service._alert_indexes_lock = asyncio.Lock()
    monkeypatch.setattr(alert_service, "ensure_alert_indexes_in_db", fail_once)

    async def initialize_with_retry():
        with pytest.raises(RuntimeError):
            await alert_service.initialize_alert_indexes()
        await alert_service.initialize_alert_indexes()

    asyncio.run(initialize_with_retry())
    assert attempts == 2
    assert alert_service._alert_indexes_ready is True


def test_highlight_target_is_hazard_first():
    from Blue_dream_agents.alert_service import choose_highlight_target
    from Blue_dream_agents.memory_schema import MemoryEvent
    from Blue_dream_agents.safety_agent import SafetyAssessment
    from Blue_dream_agents.timezone_utils import now_local

    controller_event = MemoryEvent(
        event_id="controller-event",
        timestamp=now_local(),
        room_number=0,
        room_name="Bedroom",
        video_description="A video game controller is on the bed.",
    )
    controller_assessment = SafetyAssessment(hazard_type="controller")
    assert choose_highlight_target(controller_event, controller_assessment) is None

    boiling_event = controller_event.model_copy(
        update={
            "event_id": "boiling-event",
            "video_description": "Water is boiling unattended.",
        }
    )
    assert choose_highlight_target(boiling_event, SafetyAssessment()) == "pot"

    fire_event = controller_event.model_copy(
        update={
            "event_id": "fire-event",
            "video_description": "A small fire is visible.",
        }
    )
    assert choose_highlight_target(fire_event, SafetyAssessment()) == "flame"


def test_timezone_default_and_override(monkeypatch):
    from Blue_dream_agents import timezone_utils

    monkeypatch.delenv("TIMEZONE", raising=False)
    importlib.reload(timezone_utils)
    assert timezone_utils.LOCAL_TZ.key == "America/Los_Angeles"

    monkeypatch.setenv("TIMEZONE", "UTC")
    importlib.reload(timezone_utils)
    assert timezone_utils.LOCAL_TZ.key == "UTC"

    monkeypatch.delenv("TIMEZONE", raising=False)
    importlib.reload(timezone_utils)


def test_video_upload_processing_timeout(monkeypatch):
    from Blue_dream_agents import video_agent

    processing_file = SimpleNamespace(state="PROCESSING", name="files/test")

    class FilesStub:
        def upload(self, file):
            return processing_file

        def get(self, name):
            return processing_file

    agent = video_agent.Video_Agent.__new__(video_agent.Video_Agent)
    agent.client = SimpleNamespace(files=FilesStub())

    monotonic_values = iter([0.0, 1.0])
    monkeypatch.setattr(video_agent, "VIDEO_ANALYSIS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(video_agent.time, "monotonic", lambda: next(monotonic_values))

    with pytest.raises(TimeoutError, match="exceeded 0.01s"):
        agent._upload_video("video.mp4")


class FakeCollection:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = []

    async def find_one(self, query):
        return self.existing

    async def insert_one(self, document):
        self.inserted.append(document)
        return SimpleNamespace(inserted_id="inserted-id")


def test_consolidator_timeout_persists_partial_audio(monkeypatch):
    from Blue_dream_agents import consolidator
    from Blue_dream_agents.safety_agent import empty_safety_assessment

    collection = FakeCollection()

    async def video_stub(video_path):
        return (
            None,
            "Storage/video_recordings/camera_1/video.mp4",
            TimeoutError("video processing timed out"),
        )

    class AudioStub:
        async def transcribe_audio(self, audio_path):
            return "The patient asked where the keys were."

    async def noop(*args, **kwargs):
        return None

    async def assess(*args, **kwargs):
        return empty_safety_assessment("test")

    monkeypatch.setattr(consolidator, "ensure_events_indexes", noop)
    monkeypatch.setattr(consolidator, "get_events_collection", lambda: collection)
    monkeypatch.setattr(consolidator, "_analyze_video", video_stub)
    monkeypatch.setattr(consolidator, "Audio_agent", AudioStub)
    monkeypatch.setattr(consolidator, "assess_event_safety", assess)
    monkeypatch.setattr(consolidator, "create_alert_for_safety_assessment", noop)
    monkeypatch.setattr(consolidator, "index_memory_event", noop)

    result = asyncio.run(
        consolidator.consolidator_agent(
            "video.mp4",
            "audio.wav",
            "screenshot.jpg",
            0,
        )
    )

    assert result == "inserted-id"
    assert len(collection.inserted) == 1
    document = collection.inserted[0]
    assert document["video_description"] == "Video analysis unavailable for this recording."
    assert document["video_oss_key"] == "Storage/video_recordings/camera_1/video.mp4"
    assert document["audio_transcript"] == "The patient asked where the keys were."


def test_consolidator_duplicate_does_not_reprocess_or_insert(monkeypatch):
    from Blue_dream_agents import consolidator
    from Blue_dream_agents.timezone_utils import now_local

    existing = {
        "_id": "existing-id",
        "event_id": "existing-event",
        "timestamp": now_local(),
        "room_number": 0,
        "room_name": "Bedroom",
        "video_description": "Existing event",
        "video_path": "video.mp4",
    }
    collection = FakeCollection(existing=existing)

    class MustNotConstruct:
        def __init__(self):
            raise AssertionError("media agents must not run for a duplicate")

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(consolidator, "ensure_events_indexes", noop)
    monkeypatch.setattr(consolidator, "get_events_collection", lambda: collection)
    monkeypatch.setattr(consolidator, "Audio_agent", MustNotConstruct)
    monkeypatch.setattr(consolidator, "index_memory_event", noop)

    result = asyncio.run(
        consolidator.consolidator_agent(
            "video.mp4",
            "audio.wav",
            "screenshot.jpg",
            0,
        )
    )

    assert result == "existing-id"
    assert collection.inserted == []
