"""Utilities for writing capture clips to disk."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Union

import numpy as np

import cv2
import ffmpeg

try:  # pragma: no cover - optional dependency
    from Gemini_read import gemini_client
except Exception:  # pragma: no cover - optional dependency
    gemini_client = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from SceneResolver import resolver as scene_resolver
except Exception:  # pragma: no cover - optional dependency
    scene_resolver = None  # type: ignore[assignment]


_LOGGER = logging.getLogger(__name__)


@dataclass
class ClipContext:
    """Runtime state for an in-progress clip."""

    clip_id: str
    clip_dir: Path
    metadata: Dict[str, object] = field(default_factory=dict)
    raw_paths: Dict[str, Path] = field(default_factory=dict)
    final_paths: Dict[str, Path] = field(default_factory=dict)
    writers: Dict[str, cv2.VideoWriter] = field(default_factory=dict)
    frame_sizes: Dict[str, tuple[int, int]] = field(default_factory=dict)
    frame_counts: Dict[str, int] = field(default_factory=dict)


class ClipWriter:
    """Handle writing and post-processing captured video clips."""

    def __init__(
        self,
        output_dir: Path,
        transcripts_dir: Path,
        camera_names: Iterable[str],
        default_fps: float = 30.0,
        downscale_height: int = 480,
        camera_rooms: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.transcripts_dir = Path(transcripts_dir)
        self.camera_names = list(camera_names)
        self.default_fps = default_fps
        self.downscale_height = downscale_height
        self.camera_rooms = {
            name: (camera_rooms.get(name) if camera_rooms else name)
            for name in self.camera_names
        }

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

        self._context: Optional[ClipContext] = None

    # ------------------------------------------------------------------
    # Clip lifecycle helpers
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        """Whether a clip is currently being recorded."""

        return self._context is not None

    @property
    def clip_id(self) -> Optional[str]:
        """Return the identifier of the current clip if any."""

        return None if self._context is None else self._context.clip_id

    @property
    def clip_directory(self) -> Optional[Path]:
        """Return the directory containing the active clip files."""

        return None if self._context is None else self._context.clip_dir

    def start_clip(self, clip_id: Optional[str] = None, metadata: Optional[Mapping[str, object]] = None) -> str:
        """Start recording a new clip.

        Args:
            clip_id: Optional explicit clip identifier. If omitted a timestamped
                identifier is generated.
            metadata: Arbitrary metadata that should be attached to the clip and
                forwarded to analyzers.

        Returns:
            The identifier of the clip that was started.
        """

        if self._context is not None:
            raise RuntimeError("A clip is already active")

        clip_id = clip_id or datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
        clip_dir = self.output_dir / clip_id
        clip_dir.mkdir(parents=True, exist_ok=True)

        context = ClipContext(
            clip_id=clip_id,
            clip_dir=clip_dir,
            metadata=dict(metadata or {}),
        )
        self._context = context

        _LOGGER.info("Started clip %s", clip_id)
        return clip_id

    def cancel_clip(self) -> None:
        """Cancel the current clip without producing output."""

        if self._context is None:
            return

        for writer in self._context.writers.values():
            writer.release()
        self._context = None

    def write_frame(self, camera_name: str, frame: np.ndarray) -> None:
        """Write a frame for a particular camera into the current clip."""

        if self._context is None:
            raise RuntimeError("No active clip to write to")
        if camera_name not in self.camera_names:
            raise KeyError(f"Unknown camera '{camera_name}'")

        context = self._context
        height, width = frame.shape[:2]
        frame_size = (width, height)

        writer = context.writers.get(camera_name)
        if writer is None:
            fps = self.default_fps
            raw_path = context.clip_dir / f"{camera_name}_raw.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(raw_path), fourcc, fps, frame_size)
            if not writer.isOpened():  # pragma: no cover - hardware specific
                raise RuntimeError(f"Failed to open writer for {camera_name}")
            context.writers[camera_name] = writer
            context.raw_paths[camera_name] = raw_path
            context.frame_sizes[camera_name] = frame_size
            context.frame_counts[camera_name] = 0

        writer.write(frame)
        context.frame_counts[camera_name] += 1

    def close_clip(
        self,
        audio_path: Optional[Union[Path, str]] = None,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, Path]:
        """Finalize the active clip and trigger downstream analysis.

        Args:
            audio_path: Optional WAV file that should be muxed into the clip.
            metadata: Optional metadata to merge into the clip metadata prior to
                analysis.

        Returns:
            A mapping from camera name to the final processed clip path.
        """

        if self._context is None:
            raise RuntimeError("No active clip to close")

        context = self._context
        self._context = None

        if metadata:
            context.metadata.update(metadata)

        for writer in context.writers.values():
            writer.release()

        final_paths: Dict[str, Path] = {}
        for camera_name, raw_path in context.raw_paths.items():
            final_path = context.clip_dir / f"{camera_name}.mp4"
            video_input = ffmpeg.input(str(raw_path))
            scaled_video = video_input.filter("scale", -2, self.downscale_height)

            audio_file: Optional[Path] = None
            if audio_path is not None:
                audio_file = Path(audio_path)
                if not audio_file.exists():
                    _LOGGER.warning("Audio file %s does not exist; skipping mux", audio_file)
                    audio_file = None

            if audio_file is not None:
                audio_input = ffmpeg.input(str(audio_file))
                output = ffmpeg.output(
                    scaled_video,
                    audio_input,
                    str(final_path),
                    vcodec="libx264",
                    acodec="aac",
                    movflags="+faststart",
                )
            else:
                output = ffmpeg.output(
                    scaled_video, str(final_path), vcodec="libx264", movflags="+faststart"
                )

            try:
                ffmpeg.run(output, overwrite_output=True, quiet=True)
            except ffmpeg.Error:  # pragma: no cover - integration path
                _LOGGER.exception("ffmpeg failed for clip %s camera %s", context.clip_id, camera_name)
                continue

            final_paths[camera_name] = final_path
            context.final_paths[camera_name] = final_path

            try:
                raw_path.unlink()
            except OSError:
                _LOGGER.debug("Failed to remove raw clip %s", raw_path, exc_info=True)

        if not final_paths:
            _LOGGER.warning("No video produced for clip %s; skipping analysis", context.clip_id)
            return final_paths

        if gemini_client is not None:
            for camera_name, final_path in final_paths.items():
                room = self.camera_rooms.get(camera_name, camera_name)
                clip_identifier = f"{context.clip_id}_{room}"
                try:
                    analysis_result = gemini_client.analyze_clip(
                        str(final_path), clip_identifier, str(room)
                    )
                except Exception:  # pragma: no cover - external service failure
                    _LOGGER.exception(
                        "Gemini analysis failed for clip %s camera %s",
                        context.clip_id,
                        camera_name,
                    )
                    continue

                if isinstance(analysis_result, Mapping):
                    merged = dict(context.metadata)
                    if metadata:
                        merged.update(metadata)
                    merged.setdefault("camera_name", camera_name)
                    merged.setdefault("room", str(room))
                    analysis_result["metadata"] = merged

                if scene_resolver is not None and isinstance(analysis_result, Mapping):
                    try:
                        scene_resolver.ingest(analysis_result)
                    except Exception:  # pragma: no cover - external service failure
                        _LOGGER.exception(
                            "Scene resolver ingestion failed for clip %s camera %s",
                            context.clip_id,
                            camera_name,
                        )
                elif scene_resolver is None:
                    _LOGGER.debug(
                        "Scene resolver unavailable; skipping ingest for clip %s camera %s",
                        context.clip_id,
                        camera_name,
                    )

                transcript = _extract_transcript(analysis_result)
                if transcript:
                    transcript_path = self.transcripts_dir / f"{clip_identifier}.txt"
                    try:
                        transcript_path.write_text(transcript.strip() + "\n", encoding="utf-8")
                    except OSError:  # pragma: no cover - filesystem failure
                        _LOGGER.exception(
                            "Failed to write transcript for clip %s camera %s",
                            context.clip_id,
                            camera_name,
                        )
        else:
            _LOGGER.debug("Gemini client is unavailable; skipping analysis")

        _LOGGER.info("Closed clip %s", context.clip_id)
        return final_paths


def _extract_transcript(analysis_result) -> Optional[str]:
    """Attempt to pull a transcript string from an analysis result object."""

    if not analysis_result:
        return None

    if isinstance(analysis_result, str):
        return analysis_result

    if isinstance(analysis_result, Mapping):
        audio = analysis_result.get("audio")
        if isinstance(audio, Mapping):
            transcript = audio.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                return transcript
        for key in ("summary", "transcript", "text"):
            value = analysis_result.get(key)
            if isinstance(value, str) and value.strip():
                return value

    # Fall back to stringifying JSON-serialisable results.
    try:
        return json.dumps(analysis_result)
    except TypeError:  # pragma: no cover - not serialisable
        return None


__all__ = ["ClipWriter"]
