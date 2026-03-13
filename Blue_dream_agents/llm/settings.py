from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SUPPORTED_API_KEY_REGIONS = {
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ca-central-1",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "sa-east-1",
    "us-east-1",
    "us-west-2",
}


def _default_chroma_persist_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "Storage" / "chroma")


def load_project_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("set "):
            line = line[4:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_gemini_spatial_model() -> str:
    load_project_env()
    for env_name in ("GEMINI_SPATIAL_MODEL", "GEMINI_VIDEO_MODEL"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return "gemini-2.5-flash"


class ProviderSettings(BaseModel):
    """Centralized runtime settings for Bedrock-native Nova calls."""

    model_config = ConfigDict(extra="ignore")

    bedrock_auth_mode: Literal["aws_credentials", "api_key"] = Field(
        description="Selected Bedrock authentication mode"
    )
    bedrock_region: str = Field(description="Resolved Bedrock region")
    bedrock_aws_region: str = Field(default="us-east-1")
    bedrock_api_key_region: str = Field(default="us-east-1")
    aws_bearer_token_bedrock: Optional[str] = Field(
        default=None, description="Bedrock API key token if API-key auth is used"
    )
    gemini_api_key: Optional[str] = Field(
        default=None, description="Gemini key retained for video and spatial paths"
    )
    gemini_spatial_model: str = Field(default="gemini-2.5-flash")
    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    nova_router_model: str = Field(default="us.amazon.nova-2-lite-v1:0")
    nova_synthesis_model: str = Field(default="us.amazon.nova-2-lite-v1:0")
    nova_vision_model: str = Field(default="us.amazon.nova-2-lite-v1:0")
    nova_vision_fallback_model: str = Field(default="us.amazon.nova-lite-v1:0")
    nova_embedding_model: str = Field(
        default="amazon.nova-2-multimodal-embeddings-v1:0"
    )
    chroma_persist_dir: str = Field(default_factory=_default_chroma_persist_dir)
    chroma_collection_name: str = Field(default="memory_events")
    semantic_search_top_k: int = Field(default=5)
    default_temperature: float = Field(default=0.1)
    default_max_tokens: int = Field(default=1200)
    request_timeout_seconds: float = Field(default=120.0)


def _has_aws_credentials() -> bool:
    credential_signals = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    ]
    return any(os.getenv(name) for name in credential_signals)


def _resolve_regions() -> tuple[str, str]:
    configured_region = (
        os.getenv("BEDROCK_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or ""
    ).strip()

    aws_region = (
        os.getenv("BEDROCK_AWS_REGION") or configured_region or "us-east-1"
    ).strip()
    api_key_region = (
        os.getenv("BEDROCK_API_KEY_REGION") or configured_region or "us-east-1"
    ).strip()
    if api_key_region not in SUPPORTED_API_KEY_REGIONS:
        api_key_region = "us-east-1"

    return aws_region, api_key_region


@lru_cache(maxsize=1)
def get_provider_settings() -> ProviderSettings:
    load_project_env()

    aws_region, api_key_region = _resolve_regions()
    bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

    if _has_aws_credentials():
        auth_mode: Literal["aws_credentials", "api_key"] = "aws_credentials"
        bedrock_region = aws_region
    elif bearer_token:
        auth_mode = "api_key"
        bedrock_region = api_key_region
    else:
        raise RuntimeError(
            "Missing Bedrock credentials. Configure AWS credentials or "
            "set AWS_BEARER_TOKEN_BEDROCK."
        )

    return ProviderSettings(
        bedrock_auth_mode=auth_mode,
        bedrock_region=bedrock_region,
        bedrock_aws_region=aws_region,
        bedrock_api_key_region=api_key_region,
        aws_bearer_token_bedrock=bearer_token,
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_spatial_model=resolve_gemini_spatial_model(),
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        nova_router_model=os.getenv(
            "NOVA_ROUTER_MODEL", "us.amazon.nova-2-lite-v1:0"
        ),
        nova_synthesis_model=os.getenv(
            "NOVA_SYNTHESIS_MODEL", "us.amazon.nova-2-lite-v1:0"
        ),
        nova_vision_model=os.getenv(
            "NOVA_VISION_MODEL", "us.amazon.nova-2-lite-v1:0"
        ),
        nova_vision_fallback_model=os.getenv(
            "NOVA_VISION_FALLBACK_MODEL", "us.amazon.nova-lite-v1:0"
        ),
        nova_embedding_model=os.getenv(
            "NOVA_EMBEDDING_MODEL", "amazon.nova-2-multimodal-embeddings-v1:0"
        ),
        chroma_persist_dir=os.getenv(
            "CHROMA_PERSIST_DIR", _default_chroma_persist_dir()
        ),
        chroma_collection_name=os.getenv(
            "CHROMA_COLLECTION_NAME", "memory_events"
        ),
        semantic_search_top_k=int(os.getenv("SEMANTIC_SEARCH_TOP_K", "5")),
    )
