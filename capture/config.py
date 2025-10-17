"""Configuration helpers for the capture pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import List, Optional

try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv is not None:  # pragma: no cover - optional dependency
    load_dotenv()


@dataclass(frozen=True)
class CameraSettings:
    """Settings describing a camera input."""

    name: str
    room: str
    source: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None


@dataclass(frozen=True)
class CaptureSettings:
    """Global capture configuration values."""

    output_dir: Path
    transcripts_dir: Path
    yolo_model_path: Path
    state_path: Path
    chunk_seconds: float = 10.0
    grace_no_person_ms: int = 5_000
    min_person_confidence: float = 0.25
    downscale_height: int = 480
    enable_audio: bool = False
    audio_sample_rate: int = 16_000
    audio_channels: int = 1
    audio_device: Optional[str] = None


@dataclass(frozen=True)
class Config:
    """Top-level configuration container."""

    cameras: List[CameraSettings]
    capture: CaptureSettings


def _read_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _maybe_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _maybe_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_camera_names(raw: Optional[str]) -> List[str]:
    if not raw:
        return ["camA", "camB"]
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or ["camA", "camB"]


def _parse_downscale(raw: Optional[str]) -> int:
    if not raw:
        return 480
    value = raw.strip().lower()
    if value.endswith("p"):
        value = value[:-1]
    try:
        return int(value)
    except ValueError:
        return 480


def load_config() -> Config:
    """Load the capture configuration from environment variables."""

    camera_names = _resolve_camera_names(os.getenv("CAMERA_NAMES"))
    default_rooms = ["A", "B"]

    cameras: List[CameraSettings] = []
    global_fps = _maybe_float(os.getenv("FPS"))
    for index, room in enumerate(default_rooms):
        name = camera_names[index] if index < len(camera_names) else f"cam{room}"
        env_room = room.upper()
        source = (
            os.getenv(f"CAMERA_{env_room}")
            or os.getenv(f"{env_room}")
            or os.getenv(f"{name.upper()}_SOURCE")
            or os.getenv(f"CAMERA_{name.upper()}_SOURCE")
            or str(index)
        )
        width = _maybe_int(
            os.getenv(f"CAMERA_{env_room}_WIDTH")
            or os.getenv(f"{env_room}_WIDTH")
            or os.getenv(f"{name.upper()}_WIDTH")
        )
        height = _maybe_int(
            os.getenv(f"CAMERA_{env_room}_HEIGHT")
            or os.getenv(f"{env_room}_HEIGHT")
            or os.getenv(f"{name.upper()}_HEIGHT")
        )
        fps = _maybe_float(
            os.getenv(f"CAMERA_{env_room}_FPS")
            or os.getenv(f"{env_room}_FPS")
            or os.getenv(f"{name.upper()}_FPS")
        )
        cameras.append(
            CameraSettings(
                name=name,
                room=room,
                source=str(source),
                width=width,
                height=height,
                fps=fps or global_fps,
            )
        )

    data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser()
    output_dir = Path(os.getenv("CLIPS_DIR", data_dir / "clips")).expanduser()
    transcripts_dir = Path(
        os.getenv("TRANSCRIPTS_DIR", data_dir / "transcripts")
    ).expanduser()
    state_path = Path(os.getenv("STATE_PATH", data_dir / "state.json")).expanduser()
    yolo_model_path = Path(os.getenv("YOLO_MODEL_PATH", "yolo11n.pt")).expanduser()

    chunk_seconds = float(os.getenv("CHUNK_SECONDS", "60"))
    grace_ms = int(os.getenv("GRACE_NO_PERSON_MS", "2000"))
    min_conf = float(os.getenv("DETECTION_CONF", "0.5"))
    downscale_height = _parse_downscale(os.getenv("DOWNSCALE", "480p"))
    enable_audio = _read_bool(os.getenv("ENABLE_AUDIO"))
    audio_rate = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    audio_channels = int(os.getenv("AUDIO_CHANNELS", "1"))
    audio_device = os.getenv("AUDIO_DEVICE")

    output_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    capture_settings = CaptureSettings(
        output_dir=output_dir,
        transcripts_dir=transcripts_dir,
        yolo_model_path=yolo_model_path,
        state_path=state_path,
        chunk_seconds=chunk_seconds,
        grace_no_person_ms=grace_ms,
        min_person_confidence=min_conf,
        downscale_height=downscale_height,
        enable_audio=enable_audio,
        audio_sample_rate=audio_rate,
        audio_channels=audio_channels,
        audio_device=audio_device,
    )

    return Config(cameras=cameras, capture=capture_settings)


__all__ = ["CameraSettings", "CaptureSettings", "Config", "load_config"]
