"""Live, sanitized verification spike for the spec 0005 Qwen provider.

This script intentionally exercises the configured DashScope and private OSS
account. It prints PASS/FAIL summaries without printing credentials or signed
URL query strings. Multi-image input is checked for API evidence only; the
production video fallback remains full-video Gemini analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import cv2
import httpx
import oss2
from openai import AsyncOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = PROJECT_ROOT / "Storage/video_recordings/camera_1/camera_1_2026-01-15_16-52-28.mp4"
DEFAULT_AUDIO = PROJECT_ROOT / "Storage/audio_recordings/camera_2/camera_2_2026-01-17_19-31-05.mp3"
DEFAULT_IMAGE = PROJECT_ROOT / "Storage/screenshots/camera_1/camera_1_2026-01-15_17-09-41.jpg"
INTL_COMPATIBLE_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
INTL_NATIVE_BASE = "https://dashscope-intl.aliyuncs.com/api/v1"
CHINA_COMPATIBLE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _required_env(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "<redacted>", ""))


def _snippet(value: Any, limit: int = 360) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    text = json.dumps(value, default=str, ensure_ascii=False)
    for secret_name in (
        "DASHSCOPE_API_KEY",
        "QWEN_APIKEY",
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
    ):
        secret = os.getenv(secret_name)
        if secret:
            text = text.replace(secret, "<redacted>")
    if "Signature=" in text or "OSSAccessKeyId=" in text:
        text = text.split("?", 1)[0] + "?<redacted>"
    return text[:limit]


def _data_uri(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _video_frame_data_uris(path: Path) -> list[str]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video for multi-image spike: {path}")
    try:
        frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        indices = [0, max(0, frame_count - 1)]
        results: list[str] = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"Could not read video frame {index}")
            encoded_ok, buffer = cv2.imencode(".jpg", frame)
            if not encoded_ok:
                raise RuntimeError(f"Could not encode video frame {index}")
            results.append(
                "data:image/jpeg;base64,"
                + base64.b64encode(buffer.tobytes()).decode("ascii")
            )
        return results
    finally:
        capture.release()


def _oss_endpoint() -> str:
    endpoint = _required_env("OSS_ENDPOINT").rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint


def _oss_bucket() -> oss2.Bucket:
    auth = oss2.Auth(
        _required_env("OSS_ACCESS_KEY_ID"),
        _required_env("OSS_ACCESS_KEY_SECRET"),
    )
    return oss2.Bucket(auth, _oss_endpoint(), _required_env("OSS_BUCKET"))


def _object_key(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"Spike media must be below the project root: {path}") from exc


def _upload_and_sign(path: Path, ttl: int = 3600) -> tuple[str, str]:
    bucket = _oss_bucket()
    key = _object_key(path)
    if not bucket.object_exists(key):
        bucket.put_object_from_file(key, str(path))
    return key, bucket.sign_url("GET", key, ttl)


class Spike:
    def __init__(self, *, video: Path, audio: Path, image: Path) -> None:
        self.video = video
        self.audio = audio
        self.image = image
        self.api_key = _required_env("DASHSCOPE_API_KEY", "QWEN_APIKEY")
        self.base_url = (
            os.getenv("DASHSCOPE_BASE_URL") or INTL_COMPATIBLE_BASE
        ).rstrip("/")
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=180,
        )
        self.results: dict[str, dict[str, Any]] = {}
        self.text_model = "qwen3.7-plus"
        self.vision_model = "qwen3-vl-flash"
        self.spatial_model = "qwen3-vl-plus"

    async def close(self) -> None:
        await self.client.close()

    async def check(
        self, name: str, operation: Callable[[], Awaitable[Any]]
    ) -> Any | None:
        started = time.perf_counter()
        try:
            detail = await operation()
        except Exception as exc:
            elapsed = time.perf_counter() - started
            safe_error = _snippet(f"{type(exc).__name__}: {exc}", limit=280)
            self.results[name] = {
                "status": "FAIL",
                "seconds": round(elapsed, 2),
                "detail": safe_error,
            }
            print(f"FAIL {name} ({elapsed:.2f}s): {safe_error}")
            return None
        elapsed = time.perf_counter() - started
        safe_detail = _snippet(detail)
        self.results[name] = {
            "status": "PASS",
            "seconds": round(elapsed, 2),
            "detail": safe_detail,
        }
        print(f"PASS {name} ({elapsed:.2f}s): {safe_detail}")
        return detail

    async def base_url_and_text(self) -> dict[str, Any]:
        candidates = [self.base_url]
        for candidate in (INTL_COMPATIBLE_BASE, CHINA_COMPATIBLE_BASE):
            if candidate not in candidates:
                candidates.append(candidate)
        last_error: Exception | None = None
        for base_url in candidates:
            probe = AsyncOpenAI(api_key=self.api_key, base_url=base_url, timeout=60)
            try:
                response = await probe.chat.completions.create(
                    model="qwen3.7-plus",
                    messages=[{"role": "user", "content": "Reply with the word ready."}],
                    max_tokens=16,
                    extra_body={"enable_thinking": False},
                )
                self.base_url = base_url
                await self.client.close()
                self.client = AsyncOpenAI(
                    api_key=self.api_key, base_url=base_url, timeout=180
                )
                return {
                    "base_url": base_url,
                    "model": response.model,
                    "content": response.choices[0].message.content,
                }
            except Exception as exc:
                last_error = exc
            finally:
                await probe.close()
        raise RuntimeError(f"No configured DashScope base URL succeeded: {last_error}")

    async def available_models(self) -> dict[str, str]:
        async def text_candidate(model: str) -> None:
            await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply ready."}],
                max_tokens=8,
                extra_body={"enable_thinking": False},
            )

        async def vision_candidate(model: str) -> None:
            await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Is a story book visible? Answer briefly."},
                            {"type": "image_url", "image_url": {"url": _data_uri(self.image)}},
                        ],
                    }
                ],
                max_tokens=32,
                extra_body={"enable_thinking": False},
            )

        for candidate in ("qwen3.7-plus", "qwen3.6-plus", "qwen-plus"):
            try:
                await text_candidate(candidate)
                self.text_model = candidate
                break
            except Exception:
                continue
        else:
            raise RuntimeError("No text model in the documented fallback ladder is available")

        selected: dict[str, str] = {"text": self.text_model}
        for capability, candidates in {
            "vision": ("qwen3-vl-flash", "qwen-vl-max"),
            "spatial": ("qwen3-vl-plus", "qwen-vl-max"),
        }.items():
            for candidate in candidates:
                try:
                    await vision_candidate(candidate)
                    selected[capability] = candidate
                    break
                except Exception:
                    continue
            else:
                raise RuntimeError(f"No {capability} model in the fallback ladder is available")
        self.vision_model = selected["vision"]
        self.spatial_model = selected["spatial"]
        return selected

    async def json_and_thinking(self) -> dict[str, Any]:
        default_started = time.perf_counter()
        default = await self.client.chat.completions.create(
            model=self.text_model,
            messages=[{"role": "user", "content": "Reply briefly: what is two plus two?"}],
            max_tokens=64,
        )
        default_seconds = time.perf_counter() - default_started
        disabled_started = time.perf_counter()
        disabled = await self.client.chat.completions.create(
            model=self.text_model,
            messages=[
                {"role": "system", "content": "Return JSON with an integer field named answer."},
                {"role": "user", "content": "What is two plus two? Return JSON."},
            ],
            response_format={"type": "json_object"},
            max_tokens=64,
            extra_body={"enable_thinking": False},
        )
        disabled_seconds = time.perf_counter() - disabled_started
        parsed = json.loads(disabled.choices[0].message.content or "")
        default_message = default.choices[0].message
        return {
            "json": parsed,
            "default_reasoning_present": bool(
                getattr(default_message, "reasoning_content", None)
            ),
            "default_seconds": round(default_seconds, 2),
            "thinking_off_seconds": round(disabled_seconds, 2),
        }

    async def embeddings(self) -> dict[str, Any]:
        response = await self.client.embeddings.create(
            model="text-embedding-v4",
            input=["memory retrieval test"],
            dimensions=1024,
        )
        batch_ten = await self.client.embeddings.create(
            model="text-embedding-v4",
            input=[f"item {index}" for index in range(10)],
            dimensions=1024,
        )
        eleven_rejected = False
        try:
            await self.client.embeddings.create(
                model="text-embedding-v4",
                input=[f"item {index}" for index in range(11)],
                dimensions=1024,
            )
        except Exception:
            eleven_rejected = True
        return {
            "model": response.model,
            "dimensions": len(response.data[0].embedding),
            "batch_10_count": len(batch_ten.data),
            "batch_11_rejected": eleven_rejected,
        }

    async def image_and_grounding(self) -> dict[str, Any]:
        image_uri = _data_uri(self.image)
        presence = await self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Confirm whether a story book is visible and describe it briefly.",
                        },
                        {"type": "image_url", "image_url": {"url": image_uri}},
                    ],
                }
            ],
            max_tokens=120,
            extra_body={"enable_thinking": False},
        )
        grounding = await self.client.chat.completions.create(
            model=self.spatial_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Locate the visible story book. Return JSON only as "
                                '{"bbox_2d":[x1,y1,x2,y2],"label":"story book"}. '
                                "State no prose. Preserve the model's native coordinate convention."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_uri}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=120,
            extra_body={"enable_thinking": False},
        )
        grounding_text = grounding.choices[0].message.content or ""
        grounding_payload = json.loads(grounding_text)
        coords = grounding_payload.get("bbox_2d") or []
        convention = "normalized_0_1000" if coords and max(coords) <= 1000 else "absolute_pixels"
        return {
            "grounding": grounding_payload,
            "coordinate_convention": convention,
            "presence": presence.choices[0].message.content,
        }

    async def multi_image(self) -> dict[str, Any]:
        frames = _video_frame_data_uris(self.video)
        response = await self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "These are the first and last frames of one clip. Describe the visible change briefly."},
                        *[
                            {"type": "image_url", "image_url": {"url": frame}}
                            for frame in frames
                        ],
                    ],
                }
            ],
            max_tokens=100,
            extra_body={"enable_thinking": False},
        )
        return {
            "accepted_images": len(frames),
            "content": response.choices[0].message.content,
            "production_fallback": False,
        }

    async def asr(self) -> dict[str, Any]:
        audio_endpoint_supported = True
        try:
            with self.audio.open("rb") as audio_file:
                await self.client.audio.transcriptions.create(
                    model="qwen3-asr-flash", file=audio_file
                )
        except Exception:
            audio_endpoint_supported = False

        response = await self.client.chat.completions.create(
            model="qwen3-asr-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": _data_uri(self.audio)},
                        }
                    ],
                }
            ],
            max_tokens=300,
        )
        transcript = response.choices[0].message.content or ""
        if not transcript.strip():
            raise RuntimeError("Compatible-mode Qwen ASR returned an empty transcript")

        _, audio_url = await asyncio.to_thread(_upload_and_sign, self.audio)
        native_base = INTL_NATIVE_BASE if "-intl." in self.base_url else "https://dashscope.aliyuncs.com/api/v1"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        filetrans_status = "not-tested"
        async with httpx.AsyncClient(timeout=120) as native:
            submit = await native.post(
                f"{native_base}/services/audio/asr/transcription",
                headers=headers,
                json={
                    "model": "qwen3-asr-flash-filetrans",
                    "input": {"file_url": audio_url},
                    "parameters": {"channel_id": [0], "enable_itn": True},
                },
            )
            submit.raise_for_status()
            submit_json = submit.json()
            task_id = (submit_json.get("output") or {}).get("task_id")
            if task_id:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    query = await native.get(
                        f"{native_base}/tasks/{task_id}", headers=headers
                    )
                    query.raise_for_status()
                    query_json = query.json()
                    filetrans_status = (query_json.get("output") or {}).get(
                        "task_status", "UNKNOWN"
                    )
                    if filetrans_status in {"SUCCEEDED", "FAILED", "CANCELED"}:
                        break
                    await asyncio.sleep(2)
        return {
            "audio_transcriptions_endpoint": audio_endpoint_supported,
            "compatible_chat_model": response.model,
            "transcript_nonempty": bool(transcript.strip()),
            "transcript_preview": transcript[:120],
            "filetrans_status": filetrans_status,
        }

    async def tts(self) -> dict[str, Any]:
        native_base = INTL_NATIVE_BASE if "-intl." in self.base_url else "https://dashscope.aliyuncs.com/api/v1"
        async with httpx.AsyncClient(timeout=120) as native:
            response = await native.post(
                f"{native_base}/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen3-tts-flash",
                    "input": {
                        "text": "Project Memoria voice verification.",
                        "voice": "Cherry",
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
        audio = ((payload.get("output") or {}).get("audio") or {})
        return {
            "model": "qwen3-tts-flash",
            "audio_url_present": bool(audio.get("url")),
            "expires_at_present": bool(audio.get("expires_at")),
        }

    async def oss_video(self) -> dict[str, Any]:
        key, video_url = await asyncio.to_thread(_upload_and_sign, self.video)
        response = await self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Briefly describe the actions visible in this room video."},
                        {"type": "video_url", "video_url": {"url": video_url}},
                    ],
                }
            ],
            max_tokens=220,
            extra_body={"enable_thinking": False},
        )
        return {
            "object_key": key,
            "presigned_url": _safe_url(video_url),
            "model": response.model,
            "description": response.choices[0].message.content,
            "video_bytes": self.video.stat().st_size,
            "documented_url_ceiling": "2 GB / 1 hour for Qwen3-VL",
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    _load_env()
    for path in (args.video, args.audio, args.image):
        if not path.exists():
            raise FileNotFoundError(path)

    spike = Spike(video=args.video, audio=args.audio, image=args.image)
    try:
        await spike.check("1_base_url_text", spike.base_url_and_text)
        await spike.check("2_model_availability", spike.available_models)
        await spike.check("3_4_json_thinking", spike.json_and_thinking)
        await spike.check("5_embeddings", spike.embeddings)
        await spike.check("6_image_grounding", spike.image_and_grounding)
        await spike.check("7_multi_image_evidence_only", spike.multi_image)
        await spike.check("8_asr", spike.asr)
        await spike.check("8_tts", spike.tts)
        await spike.check("9_10_oss_video_limits", spike.oss_video)
    finally:
        await spike.close()

    passed = sum(result["status"] == "PASS" for result in spike.results.values())
    failed = len(spike.results) - passed
    print(f"SUMMARY passed={passed} failed={failed}")
    print(json.dumps(spike.results, indent=2, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
