import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from Capture import camera_feed
from Capture import video_processing_queue
from Capture.camera_feed import (
    CameraRig,
    FrameDetections,
    RecordingAction,
)
from Capture.video_processing_queue import VideoProcessingQueue


CAPTURE_ENV_NAMES = (
    "CAMERA_INDICES",
    "CAMERA_ROOM_MAP",
    "FALL_MODEL_PATH",
    "CAMERA_FRAME_WIDTH",
    "CAMERA_FRAME_HEIGHT",
    "CAMERA_FPS",
    "DETECTION_CONFIDENCE_THRESHOLD",
    "DETECTION_BUFFER_SECONDS",
    "FALL_STABILITY_SECONDS",
)


class FakeAudioRecorder:
    def start_recording(self, filename):
        self.started = filename

    def stop_recording(self):
        self.stopped = True


def make_rig(tmp_path: Path) -> CameraRig:
    return CameraRig(
        camera_index=1,
        room_number=0,
        capture=SimpleNamespace(),
        frame_width=640,
        frame_height=480,
        fps=20.0,
        video_output_dir=tmp_path / "video",
        audio_output_dir=tmp_path / "audio",
        screenshot_output_dir=tmp_path / "screenshots",
        audio_recorder=FakeAudioRecorder(),
    )


def fake_box(class_id: int, confidence: float, xyxy=(1, 2, 30, 40)):
    return SimpleNamespace(
        cls=[class_id],
        conf=[confidence],
        xyxy=[xyxy],
    )


def test_recording_state_start_continue_and_stop(tmp_path):
    rig = make_rig(tmp_path)
    person = FrameDetections(person_detected=True)
    absent = FrameDetections()

    assert camera_feed.update_recording_state(rig, person, 10.0) == RecordingAction.START
    rig.recording_active = True
    assert (
        camera_feed.update_recording_state(rig, absent, 11.99)
        == RecordingAction.CONTINUE
    )
    assert camera_feed.update_recording_state(rig, absent, 12.0) == RecordingAction.STOP


def test_person_reappearance_refreshes_absence_buffer(tmp_path):
    rig = make_rig(tmp_path)
    rig.recording_active = True
    rig.last_person_detected_time = 10.0

    assert (
        camera_feed.update_recording_state(
            rig, FrameDetections(person_detected=True), 11.5
        )
        == RecordingAction.CONTINUE
    )
    assert (
        camera_feed.update_recording_state(rig, FrameDetections(), 13.0)
        == RecordingAction.CONTINUE
    )


def test_fall_confirms_after_3_5_seconds_exactly_once(tmp_path):
    rig = make_rig(tmp_path)
    rig.recording_active = True
    fallen = FrameDetections(person_detected=True, fall_detected=True)

    assert camera_feed.handle_fall_state(rig, fallen, 20.0) is False
    assert camera_feed.handle_fall_state(rig, fallen, 23.49) is False
    assert camera_feed.handle_fall_state(rig, fallen, 23.5) is True
    assert camera_feed.handle_fall_state(rig, fallen, 30.0) is False
    assert rig.fall_alert_sent is True


def test_summarize_detections_consumes_all_results_and_handles_empty():
    assert camera_feed.summarize_detections([]) == FrameDetections()

    results = [
        SimpleNamespace(boxes=[fake_box(1, 0.75)]),
        SimpleNamespace(boxes=[fake_box(0, 0.90), fake_box(0, 0.50)]),
        SimpleNamespace(boxes=None),
    ]
    summary = camera_feed.summarize_detections(results)

    assert summary.person_detected is True
    assert summary.fall_detected is True
    assert len(summary.boxes) == 2


def _clear_capture_env(monkeypatch):
    monkeypatch.setattr(camera_feed, "load_project_env", lambda: None)
    for name in CAPTURE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_capture_config_defaults_are_cwd_independent(monkeypatch):
    _clear_capture_env(monkeypatch)

    config = camera_feed.load_capture_config()

    assert config.camera_indices == (1, 2)
    assert config.camera_room_map == {1: 0, 2: 1}
    assert config.model_path == (
        camera_feed.CAPTURE_ROOT / "trained-weights" / "best.pt"
    ).resolve()
    assert config.fps == 20.0
    assert config.detection_buffer_seconds == 2.0
    assert config.fall_stability_seconds == 3.5


def test_capture_config_accepts_valid_overrides(monkeypatch):
    _clear_capture_env(monkeypatch)
    monkeypatch.setenv("CAMERA_INDICES", "0,3")
    monkeypatch.setenv("CAMERA_ROOM_MAP", "0:1,3:0")
    monkeypatch.setenv("FALL_MODEL_PATH", "Capture/trained-weights/best.pt")
    monkeypatch.setenv("CAMERA_FRAME_WIDTH", "1280")
    monkeypatch.setenv("CAMERA_FRAME_HEIGHT", "720")
    monkeypatch.setenv("CAMERA_FPS", "24")

    config = camera_feed.load_capture_config()

    assert config.camera_indices == (0, 3)
    assert config.camera_room_map == {0: 1, 3: 0}
    assert config.model_path.is_absolute()
    assert (config.frame_width, config.frame_height, config.fps) == (1280, 720, 24)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CAMERA_INDICES", "1,bad"),
        ("CAMERA_INDICES", "1,1"),
        ("CAMERA_ROOM_MAP", "1=0"),
        ("CAMERA_ROOM_MAP", "1:bedroom"),
        ("CAMERA_FPS", "0"),
        ("DETECTION_CONFIDENCE_THRESHOLD", "1.5"),
    ],
)
def test_capture_config_rejects_malformed_values(monkeypatch, name, value):
    _clear_capture_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=name):
        camera_feed.load_capture_config()


def test_video_writer_uses_its_rig_dimensions(monkeypatch, tmp_path):
    rig = make_rig(tmp_path)
    rig.frame_width = 1024
    rig.frame_height = 576
    captured = {}
    writer = object()

    monkeypatch.setattr(camera_feed.cv2, "VideoWriter_fourcc", lambda *args: 123)

    def fake_writer(filename, fourcc, fps, dimensions):
        captured.update(
            filename=filename,
            fourcc=fourcc,
            fps=fps,
            dimensions=dimensions,
        )
        return writer

    monkeypatch.setattr(camera_feed.cv2, "VideoWriter", fake_writer)

    assert camera_feed.create_video_writer(rig, tmp_path / "event.mp4") is writer
    assert captured["dimensions"] == (1024, 576)
    assert captured["fps"] == 20.0


def test_video_processing_queue_loop_accepts_work_while_idle():
    processing_queue = VideoProcessingQueue()
    processing_queue.start()
    try:
        future = processing_queue.submit_coroutine(
            asyncio.sleep(0, result="responsive")
        )
        assert future.result(timeout=2.0) == "responsive"
    finally:
        processing_queue.stop()


def test_video_processing_queue_preserves_consolidator_payload(monkeypatch):
    received = {}

    async def fake_consolidator(**kwargs):
        received.update(kwargs)
        return "event-1"

    monkeypatch.setattr(
        video_processing_queue, "consolidator_agent", fake_consolidator
    )
    timestamp = datetime(2026, 7, 18, 1, 2, 3)
    processing_queue = VideoProcessingQueue()
    processing_queue.start()
    processing_queue.add_task(
        video_path="Storage/video_recordings/camera_1/event.mp4",
        audio_path="Storage/audio_recordings/camera_1/event.mp3",
        screenshot_path="Storage/screenshots/camera_1/event.jpg",
        room_number=0,
        timestamp=timestamp,
    )
    processing_queue.stop()

    assert received == {
        "video_path": "Storage/video_recordings/camera_1/event.mp4",
        "audio_path": "Storage/audio_recordings/camera_1/event.mp3",
        "screenshot_path": "Storage/screenshots/camera_1/event.jpg",
        "room_number": 0,
        "timestamp": timestamp,
    }
