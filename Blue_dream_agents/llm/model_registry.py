from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

try:
    from .settings import get_provider_settings
except ImportError:
    from settings import get_provider_settings


class ModelRegistry(BaseModel):
    """Task-to-model mapping for the active local/legacy runtime."""

    router: str
    synthesis: str
    vision: str
    vision_fallback: str
    embedding: str

    def for_task(self, task: Literal["router", "synthesis", "vision"]) -> str:
        if task == "router":
            return self.router
        if task == "synthesis":
            return self.synthesis
        return self.vision


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    settings = get_provider_settings()
    router_model = settings.nova_router_model
    synthesis_model = settings.nova_synthesis_model
    vision_model = settings.nova_vision_model
    vision_fallback_model = settings.nova_vision_fallback_model
    embedding_model = settings.nova_embedding_model
    if settings.local_llm_provider == "ollama":
        router_model = settings.gemma_text_model
        synthesis_model = settings.gemma_text_model
        vision_model = settings.gemma_vision_model
        vision_fallback_model = settings.gemma_vision_model
    if settings.embedding_provider == "ollama":
        embedding_model = settings.local_embedding_model

    return ModelRegistry(
        router=router_model,
        synthesis=synthesis_model,
        vision=vision_model,
        vision_fallback=vision_fallback_model,
        embedding=embedding_model,
    )
