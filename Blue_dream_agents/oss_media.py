"""Private Alibaba OSS bridge for full-video Qwen understanding."""

from __future__ import annotations

from pathlib import Path

import oss2

try:
    from .llm.settings import ProviderSettings, get_provider_settings
    from .media_paths import to_fs_path, to_stored_path
except ImportError:
    from llm.settings import ProviderSettings, get_provider_settings
    from media_paths import to_fs_path, to_stored_path


def normalize_oss_endpoint(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    if not value:
        raise RuntimeError("OSS_ENDPOINT is required for Qwen video analysis.")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    if value.startswith("http://"):
        value = f"https://{value.removeprefix('http://')}"
    return value


def object_key_for_video(video_path: str | Path) -> str:
    key = to_stored_path(video_path) or ""
    if not key.startswith("Storage/"):
        raise ValueError("OSS video paths must resolve to a canonical Storage/... key.")
    return key


def _get_bucket(settings: ProviderSettings | None = None) -> oss2.Bucket:
    config = settings or get_provider_settings()
    if not config.oss_access_key_id or not config.oss_access_key_secret:
        raise RuntimeError(
            "Missing OSS_ACCESS_KEY_ID or OSS_ACCESS_KEY_SECRET for Qwen video analysis."
        )
    auth = oss2.Auth(config.oss_access_key_id, config.oss_access_key_secret)
    return oss2.Bucket(
        auth,
        normalize_oss_endpoint(config.oss_endpoint),
        config.oss_bucket,
    )


def upload_video(video_path: str | Path) -> str:
    resolved = to_fs_path(video_path)
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError(f"Video path does not exist: {video_path}")
    key = object_key_for_video(video_path)
    bucket = _get_bucket()
    if not bucket.object_exists(key):
        bucket.put_object_from_file(key, str(resolved))
    return key


def presigned_url(object_key: str, ttl: int | None = None) -> str:
    key = object_key_for_video(object_key)
    settings = get_provider_settings()
    effective_ttl = settings.oss_presign_ttl_seconds if ttl is None else ttl
    if not 1 <= effective_ttl <= 86400:
        raise RuntimeError(
            "OSS presign TTL must be between 1 and 86400 seconds."
        )
    return _get_bucket(settings).sign_url("GET", key, effective_ttl)
