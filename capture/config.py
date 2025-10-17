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
        return ["cam0", "cam1"]
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or ["cam0", "cam1"]


def load_config() -> Config:
    """Load the capture configuration from environment variables."""

    camera_names = _resolve_camera_names(os.getenv("CAMERA_NAMES"))

    cameras: List[CameraSettings] = []
    for index, name in enumerate(camera_names):
        env_name = name.upper()
        source = (
            os.getenv(f"{env_name}_SOURCE")
            or os.getenv(f"CAMERA_{env_name}_SOURCE")
            or str(index)
        )
        width = _maybe_int(
            os.getenv(f"{env_name}_WIDTH")
            or os.getenv(f"CAMERA_{env_name}_WIDTH")
        )
        height = _maybe_int(
            os.getenv(f"{env_name}_HEIGHT")
            or os.getenv(f"CAMERA_{env_name}_HEIGHT")
        )
        fps = _maybe_float(
            os.getenv(f"{env_name}_FPS")
            or os.getenv(f"CAMERA_{env_name}_FPS")
        )
        cameras.append(
            CameraSettings(
                name=name,
                source=source,
                width=width,
                height=height,
                fps=fps,
            )
        )

    output_dir = Path(os.getenv("CAPTURE_OUTPUT_DIR", "captures"))
    transcripts_dir = Path(os.getenv("TRANSCRIPTS_DIR", "transcripts"))
    yolo_model_path = Path(os.getenv("YOLO_MODEL_PATH", "yolo11n.pt"))
    chunk_seconds = float(os.getenv("CHUNK_SECONDS", "10"))
    grace_ms = int(os.getenv("GRACE_NO_PERSON_MS", "5000"))
    min_conf = float(os.getenv("PERSON_CONFIDENCE_THRESHOLD", "0.25"))
    downscale_height = int(os.getenv("DOWNSCALE_HEIGHT", "480"))
    enable_audio = _read_bool(os.getenv("ENABLE_AUDIO"))
    audio_rate = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    audio_channels = int(os.getenv("AUDIO_CHANNELS", "1"))
    audio_device = os.getenv("AUDIO_DEVICE")

    output_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    capture_settings = CaptureSettings(
        output_dir=output_dir,
        transcripts_dir=transcripts_dir,
        yolo_model_path=yolo_model_path,
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
