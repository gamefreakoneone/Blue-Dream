import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


WINDOWS_LEGACY_SCREENSHOT = (
    r"C:\Users\x\Desktop\Project Memoria\Storage\screenshots\a.jpg"
)


@pytest.fixture
def workspace_tmp_dir():
    with TemporaryDirectory(prefix="media-path-test-", dir=Path.cwd()) as directory:
        yield Path(directory)


def test_legacy_windows_path_converts_to_stored_and_url():
    from Blue_dream_agents.media_paths import to_stored_path, to_url_path

    stored = to_stored_path(WINDOWS_LEGACY_SCREENSHOT)

    assert stored == "Storage/screenshots/a.jpg"
    assert to_url_path(stored) == "/storage/screenshots/a.jpg"


def test_posix_stored_capture_and_case_insensitive_paths():
    from Blue_dream_agents.media_paths import normalize_stored_path, to_url_path

    assert normalize_stored_path("/srv/memoria/Storage/video/a.mp4") == (
        "Storage/video/a.mp4"
    )
    assert normalize_stored_path("Storage/screenshots/a.jpg") == (
        "Storage/screenshots/a.jpg"
    )
    assert normalize_stored_path(r"Capture\frames\a.jpg") == "Capture/frames/a.jpg"
    assert normalize_stored_path("old/root/storage/screenshots/a.jpg") == (
        "Storage/screenshots/a.jpg"
    )
    assert to_url_path("Capture/frames/a.jpg") == "/capture/frames/a.jpg"


def test_empty_and_unmappable_url_inputs():
    from Blue_dream_agents.media_paths import (
        normalize_stored_path,
        to_fs_path,
        to_stored_path,
        to_url_path,
    )

    for value in (None, "", "   "):
        assert normalize_stored_path(value) is None
        assert to_stored_path(value) is None
        assert to_fs_path(value) is None
        assert to_url_path(value) is None

    assert normalize_stored_path("misc/image.jpg") == "misc/image.jpg"
    assert to_url_path("misc/image.jpg") is None


def test_round_trip_resolves_below_media_root(monkeypatch, workspace_tmp_dir):
    from Blue_dream_agents import media_paths

    monkeypatch.setattr(media_paths, "MEDIA_ROOT", workspace_tmp_dir)
    source = workspace_tmp_dir / "Storage" / "screenshots" / "round-trip.jpg"
    stored = media_paths.to_stored_path(source)

    assert stored == "Storage/screenshots/round-trip.jpg"
    assert media_paths.to_fs_path(stored) == source


def test_output_directory_is_media_root_relative_not_cwd(
    monkeypatch, workspace_tmp_dir
):
    from Blue_dream_agents import media_paths

    original_cwd = Path.cwd()
    media_root = workspace_tmp_dir / "media-root"
    other_cwd = workspace_tmp_dir / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.setattr(media_paths, "MEDIA_ROOT", media_root)
    monkeypatch.chdir(other_cwd)

    output_dir = media_paths.resolve_output_dir("Storage/highlighted")

    assert output_dir == media_root / "Storage" / "highlighted"
    assert output_dir.is_dir()
    assert not (other_cwd / "Storage" / "highlighted").exists()
    monkeypatch.chdir(original_cwd)


def test_memory_event_normalizes_legacy_media_paths():
    from Blue_dream_agents.memory_schema import memory_event_from_mongo

    event = memory_event_from_mongo(
        {
            "event_id": "legacy-event",
            "room_number": 0,
            "screenshot_path": WINDOWS_LEGACY_SCREENSHOT,
            "video_path": r"C:\old\root\Storage\video_recordings\a.mp4",
            "audio_path": "/old/root/Storage/audio_recordings/a.mp3",
        }
    )

    assert event.screenshot_path == "Storage/screenshots/a.jpg"
    assert event.video_path == "Storage/video_recordings/a.mp4"
    assert event.audio_path == "Storage/audio_recordings/a.mp3"


def test_new_memory_event_and_mongo_writer_store_portable_paths():
    from Blue_dream_agents.memory_schema import (
        memory_event_to_mongo,
        new_memory_event,
    )
    from Blue_dream_agents.timezone_utils import now_local

    event = new_memory_event(
        timestamp=now_local(),
        room_number=0,
        video_description="",
        room_objects=[],
        audio_transcript="",
        screenshot_path=WINDOWS_LEGACY_SCREENSHOT,
        video_path=r"C:\old\Storage\video_recordings\a.mp4",
        audio_path=r"C:\old\Storage\audio_recordings\a.mp3",
    )
    document = memory_event_to_mongo(event)

    assert document["screenshot_path"] == "Storage/screenshots/a.jpg"
    assert document["video_path"] == "Storage/video_recordings/a.mp4"
    assert document["audio_path"] == "Storage/audio_recordings/a.mp3"


def test_consolidator_dedupe_variants_match_legacy_absolute_root():
    from Blue_dream_agents.consolidator import _path_variants

    variants = _path_variants("Storage/video_recordings/camera_1/event.mp4")
    legacy = r"C:\old\Blue-Dream\Storage\video_recordings\camera_1\event.mp4"

    assert "Storage/video_recordings/camera_1/event.mp4" in variants
    assert any(
        isinstance(candidate, re.Pattern) and candidate.fullmatch(legacy)
        for candidate in variants
    )


def test_alert_serialization_returns_url_paths():
    from Blue_dream_agents.alert_service import serialize_alert

    alert = serialize_alert(
        {
            "alert_id": "alert-1",
            "image_path": r"C:\old\Storage\highlighted\hazard.png",
            "original_image_path": WINDOWS_LEGACY_SCREENSHOT,
        }
    )

    assert alert["image_path"] == "/storage/highlighted/hazard.png"
    assert alert["original_image_path"] == "/storage/screenshots/a.jpg"


def test_mocked_object_query_response_uses_url_paths(
    client, monkeypatch, api_module
):
    from Blue_dream_agents import jeeves
    from Blue_dream_agents.jeeves import QueryRoute
    from Blue_dream_agents.object_detector import SearchResult

    async def resolve_query(query, conversation_context):
        return query, None

    async def route_query(query):
        return QueryRoute(intent="object", reason="media-path contract test")

    async def object_query(query):
        return SearchResult(
            found=True,
            description="Your keys are on the table.",
            highlighted_image_path=WINDOWS_LEGACY_SCREENSHOT,
            evidence_type="current_visual_highlight",
            confidence="high",
            highlight_status="generated",
        )

    monkeypatch.setattr(jeeves, "_resolve_query_with_context", resolve_query)
    monkeypatch.setattr(jeeves, "_route_query", route_query)
    monkeypatch.setattr(jeeves, "run_object_query", object_query)
    monkeypatch.setattr(api_module, "run_single_query", jeeves.run_single_query)

    response = client.post("/query", json={"query": "Where are my keys?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["image_path"] == "/storage/screenshots/a.jpg"
    assert payload["data"]["object"]["highlighted_image_path"] == (
        "/storage/screenshots/a.jpg"
    )


def test_mocked_alert_detail_response_uses_url_paths(
    client, monkeypatch, api_module
):
    from Blue_dream_agents.alert_service import serialize_alert

    async def alert_detail(alert_id):
        return serialize_alert(
            {
                "alert_id": alert_id,
                "image_path": r"C:\old\Storage\highlighted\hazard.png",
                "original_image_path": WINDOWS_LEGACY_SCREENSHOT,
            }
        )

    monkeypatch.setattr(api_module, "get_alert", alert_detail)

    response = client.get("/alerts/alert-1")

    assert response.status_code == 200
    assert response.json()["image_path"] == "/storage/highlighted/hazard.png"
    assert response.json()["original_image_path"] == "/storage/screenshots/a.jpg"
