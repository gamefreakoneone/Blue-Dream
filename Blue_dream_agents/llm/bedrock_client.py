from __future__ import annotations

from functools import lru_cache

from botocore.config import Config

from .settings import get_provider_settings


@lru_cache(maxsize=1)
def get_bedrock_region() -> str:
    return get_provider_settings().bedrock_region


@lru_cache(maxsize=1)
def get_bedrock_boto_config() -> Config:
    settings = get_provider_settings()
    return Config(
        connect_timeout=10,
        read_timeout=int(settings.request_timeout_seconds),
        retries={"max_attempts": 3, "mode": "standard"},
    )
