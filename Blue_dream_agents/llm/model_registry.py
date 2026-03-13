from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

try:
    from .settings import get_provider_settings
except ImportError:
    from settings import get_provider_settings


class ModelRegistry(BaseModel):
    """Task-to-model mapping for the active Nova runtime."""

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
    return ModelRegistry(
        router=settings.nova_router_model,
        synthesis=settings.nova_synthesis_model,
        vision=settings.nova_vision_model,
        vision_fallback=settings.nova_vision_fallback_model,
        embedding=settings.nova_embedding_model,
    )
