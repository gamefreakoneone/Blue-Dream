from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .audio_capture import AudioRecorder
    from .video_processing_queue import VideoProcessingQueue
except ImportError:
    from audio_capture import AudioRecorder
    from video_processing_queue import VideoProcessingQueue

from Blue_dream_agents.alert_service import create_alert_sync
from Blue_dream_agents.llm.settings import load_project_env

load_project_env()

from Blue_dream_agents.media_paths import resolve_output_dir, to_stored_path
from Blue_dream_agents.timezone_utils import now_local


logger = logging.getLogger(__name__)

FALLEN_CLASS_ID = 0
NOT_FALLEN_CLASS_ID = 1
FALLEN_COLOR = (0, 0, 255)
STANDING_COLOR = (0, 255, 0)
ROOMS = {0: "Bedroom", 1: "Living Room"}


@dataclass(frozen=True)
class CaptureConfig:
    camera_indices: tuple[int, ...]
    camera_room_map: dict[int, int]
    model_path: Path
    frame_width: int
    frame_height: int
    fps: float
    confidence_threshold: float
    detection_buffer_seconds: float
    fall_stability_seconds: float


@dataclass(frozen=True)
class DetectionBox:
    class_id: int
    confidence: float
    xyxy: tuple[int, int, int, int]


@dataclass(frozen=True)
class FrameDetections:
    person_detected: bool = False
    fall_detected: bool = False
    boxes: tuple[DetectionBox, ...] = ()


class RecordingAction(str, Enum):
    IDLE = "idle"
    START = "start"
    CONTINUE = "continue"
    STOP = "stop"


@dataclass
class CameraRig:
    camera_index: int
    room_number: int
    capture: Any
    frame_width: int
    frame_height: int
    fps: float
    video_output_dir: Path
    audio_output_dir: Path
    screenshot_output_dir: Path
    audio_recorder: Any
    detection_buffer_seconds: float = 2.0
    fall_stability_seconds: float = 3.5
    video_writer: Any = None
    recording_active: bool = False
    last_person_detected_time: Optional[float] = None
    fall_start_time: Optional[float] = None
    fall_alert_sent: bool = False
    recording_start_timestamp: Optional[datetime] = None
    current_video_filename: Optional[Path] = None
    current_audio_filename: Optional[Path] = None


def _parse_positive_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero, got {value}.")
    return value


def _parse_positive_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got {raw!r}.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero, got {value}.")
    return value


def _parse_camera_indices(raw: str) -> tuple[int, ...]:
    parts = [part.strip() for part in raw.split(",")]
    if not parts or any(not part for part in parts):
        raise RuntimeError("CAMERA_INDICES must be a comma-separated list of integers.")
    try:
        indices = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise RuntimeError(
            f"CAMERA_INDICES must be a comma-separated list of integers, got {raw!r}."
        ) from exc
    if any(index < 0 for index in indices):
        raise RuntimeError("CAMERA_INDICES cannot contain negative values.")
    if len(set(indices)) != len(indices):
        raise RuntimeError("CAMERA_INDICES cannot contain duplicate values.")
    return indices


def _parse_camera_room_map(raw: str) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or item.count(":") != 1:
            raise RuntimeError(
                "CAMERA_ROOM_MAP must use comma-separated camera:room pairs."
            )
        camera_text, room_text = (part.strip() for part in item.split(":"))
        try:
            camera_index = int(camera_text)
            room_number = int(room_text)
        except ValueError as exc:
            raise RuntimeError(
                f"CAMERA_ROOM_MAP contains a non-integer pair: {item!r}."
            ) from exc
        if camera_index < 0 or room_number < 0:
            raise RuntimeError("CAMERA_ROOM_MAP cannot contain negative values.")
        if camera_index in mapping:
            raise RuntimeError(
                f"CAMERA_ROOM_MAP contains camera {camera_index} more than once."
            )
        mapping[camera_index] = room_number
    return mapping


def load_capture_config() -> CaptureConfig:
    """Load and validate capture configuration from the project environment."""

    load_project_env()
    camera_indices = _parse_camera_indices(
        (os.getenv("CAMERA_INDICES") or "1,2").strip()
    )
    camera_room_map = _parse_camera_room_map(
        (os.getenv("CAMERA_ROOM_MAP") or "1:0,2:1").strip()
    )

    configured_model_path = (os.getenv("FALL_MODEL_PATH") or "").strip()
    if configured_model_path:
        model_path = Path(configured_model_path).expanduser()
        if not model_path.is_absolute():
            model_path = PROJECT_ROOT / model_path
        model_path = model_path.resolve()
    else:
        model_path = (CAPTURE_ROOT / "trained-weights" / "best.pt").resolve()

    confidence_raw = (os.getenv("DETECTION_CONFIDENCE_THRESHOLD") or "0.50").strip()
    try:
        confidence_threshold = float(confidence_raw)
    except ValueError as exc:
        raise RuntimeError(
            "DETECTION_CONFIDENCE_THRESHOLD must be a number between 0 and 1."
        ) from exc
    if not 0 <= confidence_threshold <= 1:
        raise RuntimeError(
            "DETECTION_CONFIDENCE_THRESHOLD must be between 0 and 1."
        )

    return CaptureConfig(
        camera_indices=camera_indices,
        camera_room_map=camera_room_map,
        model_path=model_path,
        frame_width=_parse_positive_int("CAMERA_FRAME_WIDTH", 1920),
        frame_height=_parse_positive_int("CAMERA_FRAME_HEIGHT", 1080),
        fps=_parse_positive_float("CAMERA_FPS", 20.0),
        confidence_threshold=confidence_threshold,
        detection_buffer_seconds=_parse_positive_float(
            "DETECTION_BUFFER_SECONDS", 2.0
        ),
        fall_stability_seconds=_parse_positive_float("FALL_STABILITY_SECONDS", 3.5),
    )


def init_cameras(config: CaptureConfig) -> dict[int, CameraRig]:
    """Open configured cameras and retain each camera's actual dimensions."""

    rigs: dict[int, CameraRig] = {}
    for camera_index in config.camera_indices:
        capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
        if not capture.isOpened():
            print(f"Camera {camera_index} not available")
            capture.release()
            continue

        actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or config.frame_width
        actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or config.frame_height
        room_number = config.camera_room_map.get(camera_index, camera_index)
        rig = CameraRig(
            camera_index=camera_index,
            room_number=room_number,
            capture=capture,
            frame_width=actual_width,
            frame_height=actual_height,
            fps=config.fps,
            video_output_dir=resolve_output_dir(
                f"Storage/video_recordings/camera_{camera_index}"
            ),
            audio_output_dir=resolve_output_dir(
                f"Storage/audio_recordings/camera_{camera_index}"
            ),
            screenshot_output_dir=resolve_output_dir(
                f"Storage/screenshots/camera_{camera_index}"
            ),
            audio_recorder=AudioRecorder(),
            detection_buffer_seconds=config.detection_buffer_seconds,
            fall_stability_seconds=config.fall_stability_seconds,
        )
        rigs[camera_index] = rig
        print(
            f"Camera {camera_index} opened successfully at "
            f"{actual_width}x{actual_height}"
        )
    return rigs


def summarize_detections(
    results: Iterable[Any], confidence_threshold: float = 0.50
) -> FrameDetections:
    """Summarize all model results for one frame, including an empty result list."""

    valid_boxes: list[DetectionBox] = []
    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            if confidence <= confidence_threshold:
                continue
            if class_id not in (FALLEN_CLASS_ID, NOT_FALLEN_CLASS_ID):
                continue
            coordinates = tuple(int(value) for value in box.xyxy[0])
            if len(coordinates) != 4:
                continue
            valid_boxes.append(
                DetectionBox(
                    class_id=class_id,
                    confidence=confidence,
                    xyxy=coordinates,
                )
            )

    return FrameDetections(
        person_detected=bool(valid_boxes),
        fall_detected=any(box.class_id == FALLEN_CLASS_ID for box in valid_boxes),
        boxes=tuple(valid_boxes),
    )


def update_recording_state(
    rig: CameraRig, detections: FrameDetections, now: float
) -> RecordingAction:
    """Advance the pure recording state decision for one camera frame."""

    if detections.person_detected:
        rig.last_person_detected_time = now
        return RecordingAction.CONTINUE if rig.recording_active else RecordingAction.START

    if not rig.recording_active:
        return RecordingAction.IDLE
    if rig.last_person_detected_time is None:
        return RecordingAction.CONTINUE
    if now - rig.last_person_detected_time >= rig.detection_buffer_seconds:
        return RecordingAction.STOP
    return RecordingAction.CONTINUE


def handle_fall_state(
    rig: CameraRig, detections: FrameDetections, now: float
) -> bool:
    """Return True once when a fall persists for the configured stability window."""

    if not detections.fall_detected:
        rig.fall_start_time = None
        return False
    if rig.fall_start_time is None:
        rig.fall_start_time = now
        return False
    if (
        rig.recording_active
        and not rig.fall_alert_sent
        and now - rig.fall_start_time >= rig.fall_stability_seconds
    ):
        rig.fall_alert_sent = True
        return True
    return False


def create_video_writer(rig: CameraRig, filename: Path) -> Any:
    """Create a writer using this camera rig's dimensions, never another camera's."""

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(
        str(filename),
        fourcc,
        rig.fps,
        (rig.frame_width, rig.frame_height),
    )


def save_last_frame_screenshot(video_path: Path, screenshot_dir: Path) -> Optional[Path]:
    """Extract the end-of-event frame from a completed recording."""

    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            logger.error("Could not open video for screenshot: %s", video_path)
            return None
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            capture.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        ok, frame = capture.read()
        if not ok or frame is None:
            logger.error("Could not read final frame from video: %s", video_path)
            return None
        screenshot_path = screenshot_dir / f"{video_path.stem}.jpg"
        if not cv2.imwrite(str(screenshot_path), frame):
            logger.error("Could not save final-frame screenshot: %s", screenshot_path)
            return None
        print(f"Saved screenshot: {screenshot_path}")
        return screenshot_path
    finally:
        capture.release()


def _save_fall_screenshot(rig: CameraRig, frame: Any) -> Optional[Path]:
    timestamp = now_local().strftime("%Y-%m-%d_%H-%M-%S-%f")
    screenshot_path = (
        rig.screenshot_output_dir
        / f"fall_alert_{rig.camera_index}_{timestamp}.jpg"
    )
    if not cv2.imwrite(str(screenshot_path), frame):
        logger.error("Could not save fall screenshot: %s", screenshot_path)
        return None
    print(f"Fall screenshot saved: {screenshot_path}")
    return screenshot_path


def _start_recording(rig: CameraRig, frame: Any) -> None:
    frame_height, frame_width = frame.shape[:2]
    rig.frame_width = int(frame_width)
    rig.frame_height = int(frame_height)
    started_at = now_local()
    timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    video_filename = (
        rig.video_output_dir / f"camera_{rig.camera_index}_{timestamp}.mp4"
    )
    audio_filename = (
        rig.audio_output_dir / f"camera_{rig.camera_index}_{timestamp}.mp3"
    )
    writer = create_video_writer(rig, video_filename)
    if hasattr(writer, "isOpened") and not writer.isOpened():
        writer.release()
        logger.error("Could not open video writer for %s", video_filename)
        return

    rig.video_writer = writer
    rig.current_video_filename = video_filename
    rig.current_audio_filename = audio_filename
    rig.recording_start_timestamp = started_at
    rig.recording_active = True
    rig.fall_alert_sent = False
    rig.audio_recorder.start_recording(str(audio_filename))
    print(f"Started recording: {video_filename}")


def _queue_completed_recording(
    rig: CameraRig, processing_queue: VideoProcessingQueue
) -> None:
    if rig.current_video_filename is None:
        return
    screenshot_path = save_last_frame_screenshot(
        rig.current_video_filename, rig.screenshot_output_dir
    )
    processing_queue.add_task(
        video_path=to_stored_path(rig.current_video_filename) or "",
        audio_path=to_stored_path(rig.current_audio_filename) or "",
        screenshot_path=to_stored_path(screenshot_path) or "",
        room_number=rig.room_number,
        timestamp=rig.recording_start_timestamp or now_local(),
    )
    rig.current_video_filename = None
    rig.current_audio_filename = None
    rig.recording_start_timestamp = None


def _stop_recording(rig: CameraRig, processing_queue: VideoProcessingQueue) -> None:
    if rig.video_writer is not None:
        rig.video_writer.release()
        rig.video_writer = None
    rig.audio_recorder.stop_recording()
    rig.recording_active = False
    rig.fall_alert_sent = False
    rig.fall_start_time = None
    print(
        f"Stopped recording for camera {rig.camera_index} "
        f"(no detection for {rig.detection_buffer_seconds:g}s)"
    )
    _queue_completed_recording(rig, processing_queue)


def _create_fall_alert(
    rig: CameraRig,
    frame: Any,
    processing_queue: VideoProcessingQueue,
) -> None:
    room_name = ROOMS.get(rig.room_number, f"Room {rig.room_number}")
    screenshot_path = _save_fall_screenshot(rig, frame)
    future = create_alert_sync(
        loop=processing_queue.event_loop,
        alert_type="fall",
        severity="high",
        target_role="caretaker",
        title="Possible fall detected",
        body=f"A possible fall was detected in the {room_name}.",
        room_number=rig.room_number,
        room_name=room_name,
        screenshot_path=to_stored_path(screenshot_path) or "",
    )
    processing_queue.track_future(future)
    print(f"Possible fall confirmed for camera {rig.camera_index} in {room_name}")


def draw_hud(frame: Any, detections: FrameDetections, rig: CameraRig) -> None:
    """Draw detection and recording state once for the completed frame summary."""

    for box in detections.boxes:
        x1, y1, x2, y2 = box.xyxy
        if box.class_id == FALLEN_CLASS_ID:
            color = FALLEN_COLOR
            status_label = "FALLEN"
        else:
            color = STANDING_COLOR
            status_label = "Standing"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{status_label}: {box.confidence:.2f}"
        label_size, _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        )
        cv2.rectangle(
            frame,
            (x1, y1 - label_size[1] - 10),
            (x1 + label_size[0], y1),
            color,
            -1,
        )
        cv2.putText(
            frame,
            label,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

    fallen_count = sum(
        box.class_id == FALLEN_CLASS_ID for box in detections.boxes
    )
    cv2.putText(
        frame,
        f"Persons: {len(detections.boxes)} | Fallen: {fallen_count}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
    )
    if fallen_count:
        cv2.putText(
            frame,
            "! FALL DETECTED !",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 255),
            3,
        )
    if rig.recording_active:
        cv2.putText(
            frame,
            "Recording",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 135),
            2,
        )

    camera_text = f"Camera ID: {rig.camera_index}"
    text_size = cv2.getTextSize(
        camera_text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2
    )[0]
    cv2.putText(
        frame,
        camera_text,
        (frame.shape[1] - text_size[0] - 10, frame.shape[0] - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2,
    )


def _shutdown_rigs(
    rigs: dict[int, CameraRig], processing_queue: VideoProcessingQueue
) -> None:
    print("\nShutting down camera feed...")
    for rig in rigs.values():
        rig.capture.release()
        if rig.video_writer is not None:
            rig.video_writer.release()
            rig.video_writer = None
        if rig.recording_active:
            rig.audio_recorder.stop_recording()
            rig.recording_active = False
            _queue_completed_recording(rig, processing_queue)
    cv2.destroyAllWindows()
    processing_queue.stop()
    print("All cameras released and windows closed")


def camera_feed() -> None:
    """Run the thin read/infer/state/action/draw loop for configured cameras."""

    config = load_capture_config()
    if not config.model_path.exists():
        raise FileNotFoundError(f"Fall model weights not found: {config.model_path}")

    from ultralytics import YOLO

    model = YOLO(str(config.model_path))
    rigs = init_cameras(config)
    if not rigs:
        print("Error: No cameras available")
        return

    processing_queue = VideoProcessingQueue()
    processing_queue.start()
    print("Press 'q' to quit")
    try:
        while True:
            for rig in rigs.values():
                ok, frame = rig.capture.read()
                if not ok:
                    print(f"Error: Could not read frame from camera {rig.camera_index}")
                    continue

                results = model(frame, verbose=False)
                detections = summarize_detections(
                    results, confidence_threshold=config.confidence_threshold
                )
                current_time = time.monotonic()
                action = update_recording_state(rig, detections, current_time)
                if action == RecordingAction.START:
                    _start_recording(rig, frame)
                elif action == RecordingAction.STOP:
                    _stop_recording(rig, processing_queue)

                if handle_fall_state(rig, detections, current_time):
                    _create_fall_alert(rig, frame, processing_queue)

                if rig.recording_active and rig.video_writer is not None:
                    rig.video_writer.write(frame)

                draw_hud(frame, detections, rig)
                cv2.imshow(
                    f"Camera {rig.camera_index} - Fall Detection", frame
                )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        _shutdown_rigs(rigs, processing_queue)


if __name__ == "__main__":
    camera_feed()
