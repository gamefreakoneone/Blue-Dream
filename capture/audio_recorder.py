"""Optional audio recording helper using sounddevice."""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    import sounddevice as sd
    import soundfile as sf
except Exception:  # pragma: no cover - optional dependency
    sd = None  # type: ignore[assignment]
    sf = None  # type: ignore[assignment]


_LOGGER = logging.getLogger(__name__)


class AudioRecorderError(RuntimeError):
    """Base exception raised by :class:`AudioRecorder`."""


class AudioRecorderUnavailable(AudioRecorderError):
    """Raised when the required audio backends are not installed."""


@dataclass
class _RecorderState:
    file: Optional[Any]
    stream: Optional[Any]
    writer_thread: Optional[threading.Thread]
    queue: "queue.Queue[Optional[Any]]"
    path: Optional[Path]


class AudioRecorder:
    """Record audio to a WAV file in the background."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        device: Optional[str] = None,
    ) -> None:
        if sd is None or sf is None:
            raise AudioRecorderUnavailable(
                "sounddevice and soundfile are required for audio recording"
            )

        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device

        self._state = _RecorderState(
            file=None,
            stream=None,
            writer_thread=None,
            queue=queue.Queue(),
            path=None,
        )
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def start(self, path: Path) -> Path:
        """Begin recording to the given path."""

        with self._lock:
            if self._state.stream is not None:
                raise AudioRecorderError("Recorder is already running")

            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)

            sound_file = sf.SoundFile(
                str(target), mode="w", samplerate=self.sample_rate, channels=self.channels
            )
            frame_queue: "queue.Queue[Optional[Any]]" = queue.Queue()

            def _callback(indata, frames, time, status):  # pragma: no cover - hardware specific
                if status:
                    _LOGGER.warning("Audio recorder status: %s", status)
                frame_queue.put(indata.copy())

            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device,
                callback=_callback,
            )

            def _writer() -> None:
                while True:
                    chunk = frame_queue.get()
                    if chunk is None:
                        break
                    sound_file.write(chunk)

            writer_thread = threading.Thread(target=_writer, daemon=True)

            stream.start()
            writer_thread.start()

            self._state = _RecorderState(
                file=sound_file,
                stream=stream,
                writer_thread=writer_thread,
                queue=frame_queue,
                path=target,
            )

            _LOGGER.info("Audio recording started: %s", target)
            return target

    def stop(self) -> Optional[Path]:
        """Stop recording and close the WAV file."""

        with self._lock:
            if self._state.stream is None:
                return self._state.path

            if self._state.stream is not None:
                try:
                    self._state.stream.stop()
                    self._state.stream.close()
                except Exception:  # pragma: no cover - hardware specific
                    _LOGGER.exception("Failed to close audio stream")

            if self._state.queue is not None:
                self._state.queue.put(None)

            if self._state.writer_thread is not None:
                self._state.writer_thread.join()

            if self._state.file is not None:
                try:
                    self._state.file.close()
                except Exception:  # pragma: no cover - filesystem specific
                    _LOGGER.exception("Failed to close audio file")

            path = self._state.path
            self._state = _RecorderState(
                file=None,
                stream=None,
                writer_thread=None,
                queue=queue.Queue(),
                path=None,
            )

            _LOGGER.info("Audio recording stopped: %s", path)
            return path


__all__ = ["AudioRecorder", "AudioRecorderError", "AudioRecorderUnavailable"]
