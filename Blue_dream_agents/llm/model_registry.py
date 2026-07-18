from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import BaseModel

try:
    from .settings import ProviderSettings, get_provider_settings
except ImportError:
    from settings import ProviderSettings, get_provider_settings


TaskName = Literal[
    "text",
    "router",
    "synthesis",
    "judge",
    "vision",
    "spatial",
    "video",
    "embedding",
    "transcribe",
    "tts",
]


class TaskTarget(BaseModel):
    provider: Literal["qwen", "openai", "ollama", "gemini", "none"]
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    supports_json_object: bool = False
    supports_json_schema: bool = False
    embedding_dim: Optional[int] = None
    disable_thinking: bool = False


_PRESETS = {
    "qwen": {
        "text": "qwen3.7-plus",
        "synthesis": "qwen3.7-plus",
        "vision": "qwen3-vl-flash",
        "spatial": "qwen3-vl-plus",
        "video": "qwen3-vl-flash",
        "embedding": "text-embedding-v4",
        "embedding_dim": 1024,
        "transcribe": "qwen3-asr-flash",
        "tts": "qwen3-tts-flash",
    },
    "openai": {
        "text": "gpt-5.6",
        "synthesis": "gpt-5.6",
        "vision": "gpt-5.6",
        "video": "gpt-5.6",
        "embedding": "text-embedding-3-small",
        "embedding_dim": 1536,
        "transcribe": "gpt-4o-transcribe",
        "tts": "gpt-4o-mini-tts",
    },
    "ollama": {
        "text": "gemma4:e2b",
        "synthesis": "gemma4:e2b",
        "vision": "gemma4:e2b",
        "video": "gemma4:e2b",
        "embedding": "nomic-embed-text",
        "embedding_dim": 768,
        "transcribe": "",
        "tts": "",
    },
}


def _provider_for_task(task: TaskName, settings: ProviderSettings) -> str:
    if task == "embedding":
        return settings.embedding_provider
    if task == "video":
        return settings.video_provider
    if task == "spatial":
        return settings.spatial_provider
    if task == "transcribe":
        return settings.transcribe_provider
    if task == "tts":
        return settings.tts_provider
    return settings.llm_provider


def _model_for_task(
    task: TaskName, provider: str, settings: ProviderSettings
) -> str:
    if provider == "gemini":
        return (
            settings.gemini_video_model
            if task == "video"
            else settings.gemini_spatial_model
        )
    if provider == "none":
        return ""

    presets = _PRESETS[provider]
    if task == "embedding":
        return settings.llm_embedding_model or str(presets["embedding"])
    if task == "transcribe":
        return settings.llm_transcribe_model or str(presets["transcribe"])
    if task == "tts":
        return settings.llm_tts_model or str(presets["tts"])
    if task == "video":
        return settings.llm_video_model or str(presets["video"])
    if task == "spatial":
        return settings.llm_spatial_model or str(presets.get("spatial", presets["vision"]))
    if task == "vision":
        return settings.llm_vision_model or str(presets["vision"])
    if task == "synthesis":
        return (
            settings.llm_synthesis_model
            or settings.llm_text_model
            or str(presets["synthesis"])
        )
    return settings.llm_text_model or str(presets["text"])


def _connection_for_provider(
    provider: str, task: TaskName, settings: ProviderSettings
) -> tuple[Optional[str], Optional[str]]:
    if provider == "qwen":
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "Missing DASHSCOPE_API_KEY (QWEN_APIKEY is accepted as a fallback) "
                f"for {task} provider 'qwen'."
            )
        return settings.dashscope_base_url, settings.dashscope_api_key
    if provider == "openai":
        api_key = settings.openai_api_key
        missing_name = "OPENAI_API_KEY"
        if task == "transcribe":
            api_key = settings.openai_transcribe_api_key or api_key
            missing_name = "OPENAI_TRANSCRIBE_API_KEY or OPENAI_API_KEY"
        if not api_key:
            raise RuntimeError(
                f"Missing {missing_name} for {task} provider 'openai'."
            )
        return settings.openai_base_url, api_key
    if provider == "ollama":
        base_url = settings.ollama_base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url, "ollama"
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(
                f"Missing GEMINI_API_KEY for {task} provider 'gemini'."
            )
        return None, settings.gemini_api_key
    return None, None


def resolve(task: str) -> TaskTarget:
    normalized = task.strip().lower()
    allowed = {
        "text",
        "router",
        "synthesis",
        "judge",
        "vision",
        "spatial",
        "video",
        "embedding",
        "transcribe",
        "tts",
    }
    if normalized not in allowed:
        raise ValueError(
            f"Unknown LLM task {task!r}; expected one of: {', '.join(sorted(allowed))}."
        )

    task_name: TaskName = normalized  # type: ignore[assignment]
    settings = get_provider_settings()
    provider = _provider_for_task(task_name, settings)
    model = _model_for_task(task_name, provider, settings)
    base_url, api_key = _connection_for_provider(provider, task_name, settings)
    embedding_dim = None
    if task_name == "embedding":
        embedding_dim = settings.llm_embedding_dim or int(
            _PRESETS[provider]["embedding_dim"]
        )

    return TaskTarget(
        provider=provider,  # type: ignore[arg-type]
        model=model,
        base_url=base_url,
        api_key=api_key,
        supports_json_object=provider in {"qwen", "ollama"},
        supports_json_schema=provider == "openai",
        embedding_dim=embedding_dim,
        disable_thinking=provider == "qwen" and task_name in {"router", "judge"},
    )


class ModelRegistry(BaseModel):
    """Compatibility view used by the existing routing modules."""

    router: str
    synthesis: str
    vision: str
    vision_fallback: str
    embedding: str

    def for_task(self, task: Literal["router", "synthesis", "vision"]) -> str:
        return getattr(self, task)


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    vision = resolve("vision").model
    return ModelRegistry(
        router=resolve("router").model,
        synthesis=resolve("synthesis").model,
        vision=vision,
        vision_fallback=vision,
        embedding=resolve("embedding").model,
    )
