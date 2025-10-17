"""Capture pipeline that records from two cameras with YOLO person detection."""
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from capture.clip_writer import ClipWriter
from capture.config import CameraSettings, Config, load_config

try:  # pragma: no cover - optional dependency
    from capture.audio_recorder import AudioRecorder, AudioRecorderUnavailable
except Exception:  # pragma: no cover - optional dependency
    AudioRecorder = None  # type: ignore[assignment]
    AudioRecorderUnavailable = Exception  # type: ignore[assignment]


_LOGGER = logging.getLogger(__name__)


@dataclass
class _CameraRuntime:
    name: str
    settings: CameraSettings
    capture: cv2.VideoCapture


def _as_source(value: str):
    try:
        if value.strip() == "":
            return 0
        idx = int(value)
        return idx
    except ValueError:
        return value


def _open_camera(settings: CameraSettings) -> cv2.VideoCapture:
    source = _as_source(settings.source)
    cap = cv2.VideoCapture(source)
    if settings.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
    if settings.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)
    if settings.fps:
        cap.set(cv2.CAP_PROP_FPS, settings.fps)
    if not cap.isOpened():  # pragma: no cover - hardware specific
        raise RuntimeError(f"Failed to open camera {settings.name} ({settings.source})")
    return cap


def _load_model(config: Config) -> YOLO:
    model_path = config.capture.yolo_model_path
    if not model_path.exists():
        raise FileNotFoundError(f"YOLO model not found at {model_path}")
    return YOLO(str(model_path))


def _detect_people(model: YOLO, frames: Dict[str, np.ndarray], threshold: float) -> Dict[str, int]:
    if not frames:
        return {name: 0 for name in frames.keys()}

    names = list(frames.keys())
    inputs = [frames[name] for name in names]
    results = model(inputs, verbose=False)

    counts: Dict[str, int] = {}
    for name, result in zip(names, results):
        count = 0
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            counts[name] = 0
            continue
        classes = getattr(boxes, "cls", None)
        confidences = getattr(boxes, "conf", None)
        if classes is None or confidences is None:
            counts[name] = 0
            continue
        for cls_value, conf_value in zip(classes, confidences):
            try:
                cls_idx = int(cls_value.item())  # type: ignore[attr-defined]
            except AttributeError:
                cls_idx = int(cls_value)
            try:
                conf = float(conf_value.item())  # type: ignore[attr-defined]
            except AttributeError:
                conf = float(conf_value)
            if cls_idx == 0 and conf >= threshold:
                count += 1
        counts[name] = count

    return counts


def _setup_audio(config: Config) -> Optional[AudioRecorder]:
    if not config.capture.enable_audio or AudioRecorder is None:
        return None

    try:
        return AudioRecorder(
            sample_rate=config.capture.audio_sample_rate,
            channels=config.capture.audio_channels,
            device=config.capture.audio_device,
        )
    except AudioRecorderUnavailable as exc:  # pragma: no cover - optional dependency
        _LOGGER.warning("Audio recorder unavailable: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - hardware specific
        _LOGGER.exception("Failed to initialise audio recorder: %s", exc)
        return None


def _finalise_clip(
    writer: ClipWriter,
    audio_recorder: Optional[AudioRecorder],
    audio_running: bool,
    metadata: Optional[Dict[str, object]] = None,
) -> bool:
    audio_path: Optional[Path] = None
    if audio_recorder is not None and audio_running:
        audio_path = audio_recorder.stop()
    clip_id = writer.clip_id
    try:
        writer.close_clip(audio_path=audio_path, metadata=metadata)
    except Exception:
        _LOGGER.exception("Failed to close clip %s", clip_id)
        return False
    return True


def _start_clip(
    writer: ClipWriter,
    metadata: Optional[Dict[str, object]] = None,
    audio_recorder: Optional[AudioRecorder] = None,
) -> Tuple[bool, bool]:
    try:
        writer.start_clip(metadata=metadata)
    except Exception:
        _LOGGER.exception("Failed to start clip")
        return False, False

    audio_started = False
    if audio_recorder is not None:
        clip_dir = writer.clip_directory
        if clip_dir is not None:
            audio_target = clip_dir / "audio.wav"
            try:
                audio_recorder.start(audio_target)
                audio_started = True
            except Exception:  # pragma: no cover - hardware specific
                _LOGGER.exception("Failed to start audio recording")
    return True, audio_started


def run_capture(config: Config) -> None:
    if not config.cameras:
        raise ValueError("No cameras configured")

    model = _load_model(config)

    runtimes: Dict[str, _CameraRuntime] = {}
    for camera in config.cameras:
        cap = _open_camera(camera)
        runtimes[camera.name] = _CameraRuntime(name=camera.name, settings=camera, capture=cap)

    fps_candidates = [c.fps for c in config.cameras if c.fps]
    default_fps = fps_candidates[0] if fps_candidates else 30.0
    writer = ClipWriter(
        output_dir=config.capture.output_dir,
        transcripts_dir=config.capture.transcripts_dir,
        camera_names=[c.name for c in config.cameras],
        default_fps=default_fps,
        downscale_height=config.capture.downscale_height,
    )
    audio_recorder = _setup_audio(config)
    audio_running = False

    grace_ms = config.capture.grace_no_person_ms
    chunk_seconds = config.capture.chunk_seconds
    threshold = config.capture.min_person_confidence

    last_person_time: Optional[float] = None
    chunk_deadline: Optional[float] = None
    clip_sequence = 0

    try:
        while True:
            frames: Dict[str, np.ndarray] = {}
            for runtime in runtimes.values():
                ok, frame = runtime.capture.read()
                if not ok:
                    _LOGGER.warning("Failed to read frame from camera %s", runtime.name)
                    continue
                frames[runtime.name] = frame

            if not frames:
                time.sleep(0.1)
                continue

            person_counts = _detect_people(model, frames, threshold)
            persons_present = any(count > 0 for count in person_counts.values())
            now = time.time()
            if persons_present:
                last_person_time = now

            if persons_present and not writer.active:
                clip_sequence += 1
                metadata = {
                    "sequence": clip_sequence,
                    "started_at": datetime.utcnow().isoformat(),
                    "initial_counts": person_counts,
                }
                started, audio_started = _start_clip(
                    writer, metadata=metadata, audio_recorder=audio_recorder
                )
                if started:
                    chunk_deadline = now + chunk_seconds
                    audio_running = audio_started

            if writer.active:
                for name, frame in frames.items():
                    try:
                        writer.write_frame(name, frame)
                    except Exception:
                        _LOGGER.exception("Failed to write frame for camera %s", name)

                if persons_present and chunk_deadline is not None and now >= chunk_deadline:
                    metadata = {
                        "ended_at": datetime.utcnow().isoformat(),
                        "reason": "chunk",
                        "person_counts": person_counts,
                    }
                    closed = _finalise_clip(
                        writer,
                        audio_recorder,
                        audio_running,
                        metadata=metadata,
                    )
                    audio_running = False
                    chunk_deadline = None
                    if closed and persons_present:
                        clip_sequence += 1
                        metadata = {
                            "sequence": clip_sequence,
                            "started_at": datetime.utcnow().isoformat(),
                            "initial_counts": person_counts,
                        }
                        started, audio_started = _start_clip(
                            writer, metadata=metadata, audio_recorder=audio_recorder
                        )
                        if started:
                            chunk_deadline = now + chunk_seconds
                            audio_running = audio_started
                    continue

                if not persons_present and last_person_time is not None:
                    idle_ms = (now - last_person_time) * 1000
                    if idle_ms >= grace_ms:
                        metadata = {
                            "ended_at": datetime.utcnow().isoformat(),
                            "reason": "idle",
                            "person_counts": person_counts,
                        }
                        _finalise_clip(
                            writer,
                            audio_recorder,
                            audio_running,
                            metadata=metadata,
                        )
                        audio_running = False
                        chunk_deadline = None
                        last_person_time = None

    except KeyboardInterrupt:  # pragma: no cover - manual interrupt
        _LOGGER.info("Interrupted by user, stopping capture")
    finally:
        if writer.active:
            metadata = {
                "ended_at": datetime.utcnow().isoformat(),
                "reason": "shutdown",
            }
            _finalise_clip(writer, audio_recorder, audio_running, metadata=metadata)
        for runtime in runtimes.values():
            runtime.capture.release()


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Capture two cameras with YOLO person detection")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    config = load_config()
    run_capture(config)


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
