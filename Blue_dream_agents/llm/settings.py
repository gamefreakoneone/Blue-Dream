from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


ProviderName = Literal["qwen", "openai", "ollama"]
T = TypeVar("T", bound=str)


def _default_chroma_persist_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "Storage" / "chroma")


def load_project_env() -> None:
    """Load the repository .env without overriding process environment values."""
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


def _env_choice(name: str, default: T, allowed: set[str]) -> T:
    value = (os.getenv(name) or default).strip().lower()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise RuntimeError(f"Invalid {name}={value!r}; expected one of: {choices}.")
    return value  # type: ignore[return-value]


def _env_optional(name: str) -> Optional[str]:
    value = (os.getenv(name) or "").strip()
    return value or None


def _env_optional_int(name: str) -> Optional[int]:
    value = _env_optional(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}.") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero, got {parsed}.")
    return parsed


def _env_positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero, got {value}.")
    return value


def _env_positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero, got {value}.")
    return value


def _env_unit_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not 0.0 <= value <= 1.0:
        raise RuntimeError(f"{name} must be between 0 and 1, got {value}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_float(name: str) -> Optional[float]:
    value = _env_optional(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def resolve_gemini_spatial_model() -> str:
    load_project_env()
    for env_name in ("GEMINI_SPATIAL_MODEL", "GEMINI_VIDEO_MODEL"):
        value = _env_optional(env_name)
        if value:
            return value
    return "gemini-2.5-flash"


class ProviderSettings(BaseModel):
    """Centralized provider and application runtime settings."""

    model_config = ConfigDict(extra="ignore")

    llm_provider: ProviderName = "qwen"
    embedding_provider: ProviderName = "qwen"
    video_provider: Literal["qwen", "gemini"] = "qwen"
    spatial_provider: Literal["qwen", "gemini"] = "qwen"
    transcribe_provider: Literal["qwen", "openai"] = "qwen"
    tts_provider: Literal["qwen", "openai", "none"] = "none"

    dashscope_api_key: Optional[str] = None
    dashscope_base_url: str = (
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    openai_api_key: Optional[str] = None
    openai_transcribe_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"

    llm_text_model: Optional[str] = None
    llm_synthesis_model: Optional[str] = None
    llm_vision_model: Optional[str] = None
    llm_spatial_model: Optional[str] = None
    llm_video_model: Optional[str] = None
    llm_embedding_model: Optional[str] = None
    llm_embedding_dim: Optional[int] = None
    llm_transcribe_model: Optional[str] = None
    llm_tts_model: Optional[str] = None
    embed_batch_size: int = 10

    gemini_api_key: Optional[str] = None
    gemini_video_model: str = "gemini-3-flash-preview"
    gemini_spatial_model: str = "gemini-2.5-flash"

    oss_access_key_id: Optional[str] = None
    oss_access_key_secret: Optional[str] = None
    oss_bucket: str = "memoria"
    oss_endpoint: str = "oss-ap-southeast-1.aliyuncs.com"
    oss_presign_ttl_seconds: int = 3600

    mongodb_uri: str = "mongodb://localhost:27017"
    chroma_persist_dir: str = Field(default_factory=_default_chroma_persist_dir)
    semantic_search_top_k: int = 5
    consolidation_age_days: int = 2
    consolidation_importance_max: float = 0.5
    consolidation_min_events: int = 3
    consolidate_on_startup: bool = False
    recall_half_life_days: float = 14.0
    recall_token_budget: int = 2000
    safety_agent_enabled: bool = True
    safety_alert_min_severity: str = "medium"
    firebase_project_id: Optional[str] = None
    firebase_credentials_path: Optional[str] = None
    firebase_android_package: Optional[str] = None
    patient_home_lat: Optional[float] = None
    patient_home_lng: Optional[float] = None
    patient_geofence_radius_meters: float = 100.0
    default_temperature: float = 0.1
    default_max_tokens: int = 1200
    request_timeout_seconds: float = 120.0


@lru_cache(maxsize=1)
def get_provider_settings() -> ProviderSettings:
    load_project_env()

    llm_provider = _env_choice(
        "LLM_PROVIDER", "qwen", {"qwen", "openai", "ollama"}
    )
    embedding_provider = _env_choice(
        "EMBEDDING_PROVIDER",
        llm_provider,
        {"qwen", "openai", "ollama"},
    )

    return ProviderSettings(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        video_provider=_env_choice(
            "VIDEO_PROVIDER", "qwen", {"qwen", "gemini"}
        ),
        spatial_provider=_env_choice(
            "SPATIAL_PROVIDER", "qwen", {"qwen", "gemini"}
        ),
        transcribe_provider=_env_choice(
            "TRANSCRIBE_PROVIDER", "qwen", {"qwen", "openai"}
        ),
        tts_provider=_env_choice(
            "TTS_PROVIDER", "none", {"qwen", "openai", "none"}
        ),
        dashscope_api_key=(
            _env_optional("DASHSCOPE_API_KEY") or _env_optional("QWEN_APIKEY")
        ),
        dashscope_base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/"),
        openai_api_key=_env_optional("OPENAI_API_KEY"),
        openai_transcribe_api_key=_env_optional("OPENAI_TRANSCRIBE_API_KEY"),
        openai_base_url=os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/"),
        ollama_base_url=os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        ).rstrip("/"),
        llm_text_model=_env_optional("LLM_TEXT_MODEL"),
        llm_synthesis_model=_env_optional("LLM_SYNTHESIS_MODEL"),
        llm_vision_model=_env_optional("LLM_VISION_MODEL"),
        llm_spatial_model=_env_optional("LLM_SPATIAL_MODEL"),
        llm_video_model=_env_optional("LLM_VIDEO_MODEL"),
        llm_embedding_model=_env_optional("LLM_EMBEDDING_MODEL"),
        llm_embedding_dim=_env_optional_int("LLM_EMBEDDING_DIM"),
        llm_transcribe_model=_env_optional("LLM_TRANSCRIBE_MODEL"),
        llm_tts_model=_env_optional("LLM_TTS_MODEL"),
        embed_batch_size=int(os.getenv("EMBED_BATCH_SIZE", "10")),
        gemini_api_key=_env_optional("GEMINI_API_KEY"),
        gemini_video_model=os.getenv(
            "GEMINI_VIDEO_MODEL", "gemini-3-flash-preview"
        ),
        gemini_spatial_model=resolve_gemini_spatial_model(),
        oss_access_key_id=_env_optional("OSS_ACCESS_KEY_ID"),
        oss_access_key_secret=_env_optional("OSS_ACCESS_KEY_SECRET"),
        oss_bucket=os.getenv("OSS_BUCKET", "memoria"),
        oss_endpoint=os.getenv(
            "OSS_ENDPOINT", "oss-ap-southeast-1.aliyuncs.com"
        ),
        oss_presign_ttl_seconds=int(
            os.getenv("OSS_PRESIGN_TTL_SECONDS", "3600")
        ),
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        chroma_persist_dir=os.getenv(
            "CHROMA_PERSIST_DIR", _default_chroma_persist_dir()
        )
        or _default_chroma_persist_dir(),
        semantic_search_top_k=int(os.getenv("SEMANTIC_SEARCH_TOP_K", "5")),
        consolidation_age_days=_env_positive_int("CONSOLIDATION_AGE_DAYS", 2),
        consolidation_importance_max=_env_unit_float(
            "CONSOLIDATION_IMPORTANCE_MAX", 0.5
        ),
        consolidation_min_events=_env_positive_int(
            "CONSOLIDATION_MIN_EVENTS", 3
        ),
        consolidate_on_startup=_env_bool("CONSOLIDATE_ON_STARTUP", False),
        recall_half_life_days=_env_positive_float("RECALL_HALF_LIFE_DAYS", 14.0),
        recall_token_budget=_env_positive_int("RECALL_TOKEN_BUDGET", 2000),
        safety_agent_enabled=_env_bool("SAFETY_AGENT_ENABLED", True),
        safety_alert_min_severity=os.getenv(
            "SAFETY_ALERT_MIN_SEVERITY", "medium"
        ).strip().lower(),
        firebase_project_id=_env_optional("FIREBASE_PROJECT_ID"),
        firebase_credentials_path=_env_optional("FIREBASE_CREDENTIALS_PATH"),
        firebase_android_package=_env_optional("FIREBASE_ANDROID_PACKAGE"),
        patient_home_lat=_env_float("PATIENT_HOME_LAT"),
        patient_home_lng=_env_float("PATIENT_HOME_LNG"),
        patient_geofence_radius_meters=(
            _env_float("PATIENT_GEOFENCE_RADIUS_METERS") or 100.0
        ),
        default_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.1")),
        default_max_tokens=int(os.getenv("LLM_DEFAULT_MAX_TOKENS", "1200")),
        request_timeout_seconds=float(
            os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120")
        ),
    )
