from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional, Sequence, TypeVar

from pydantic import BaseModel

try:
    from .bedrock_client import get_bedrock_boto_config, get_bedrock_region
    from .settings import get_provider_settings
except ImportError:
    from bedrock_client import get_bedrock_boto_config, get_bedrock_region
    from settings import get_provider_settings

try:
    from strands import Agent, tool as _strands_tool
except ImportError:
    Agent = None
    _strands_tool = None

try:
    from strands.models import BedrockModel
except ImportError:
    try:
        from strands.models.bedrock import BedrockModel
    except ImportError:
        BedrockModel = None


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


def strands_tool(func=None, **kwargs):
    """Safe wrapper around the Strands tool decorator."""

    if _strands_tool is None:
        if func is not None:
            return func

        def decorator(inner):
            return inner

        return decorator

    if func is not None:
        return _strands_tool(func, **kwargs)
    return _strands_tool(**kwargs)


def ensure_strands_available() -> None:
    if Agent is None or BedrockModel is None:
        raise RuntimeError(
            "Strands Bedrock support is not installed. Install "
            "`strands-agents[bedrock]` before running the Nova runtime."
        )


def _candidate_model_ids(model_id: str) -> list[str]:
    candidates = [model_id]
    if model_id.startswith("amazon."):
        candidates.extend([f"us.{model_id}", f"global.{model_id}"])
    elif model_id.startswith("us.amazon.") or model_id.startswith("global.amazon."):
        candidates.append(model_id.split(".", 1)[1])

    deduped = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _is_model_not_found_error(error: Exception) -> bool:
    text = str(error).lower()
    needles = [
        "does not exist",
        "not_found",
        "unknown model",
        "could not resolve the foundation model",
        "invalid model identifier",
        "resource not found",
    ]
    return any(needle in text for needle in needles)


def create_agent(
    *,
    system_prompt: str,
    model_id: str,
    tools: Optional[Sequence[Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
):
    ensure_strands_available()
    settings = get_provider_settings()
    model = BedrockModel(
        model_id=model_id,
        region_name=get_bedrock_region(),
        temperature=settings.default_temperature if temperature is None else temperature,
        max_tokens=settings.default_max_tokens if max_tokens is None else max_tokens,
        boto_client_config=get_bedrock_boto_config(),
    )
    return Agent(model=model, system_prompt=system_prompt, tools=list(tools or []))


def _extract_text_from_result(result: Any) -> str:
    message = getattr(result, "message", None)
    if isinstance(message, dict):
        content = message.get("content", [])
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                text = block.get("text")
                if text:
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    return str(result).strip()


async def invoke_text(
    *,
    prompt: Any,
    system_prompt: str,
    model_id: str,
    tools: Optional[Sequence[Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    last_error: Optional[Exception] = None
    for candidate_model_id in _candidate_model_ids(model_id):
        try:
            agent = create_agent(
                system_prompt=system_prompt,
                model_id=candidate_model_id,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = await agent.invoke_async(prompt)
            return _extract_text_from_result(result)
        except Exception as exc:
            last_error = exc
            if not _is_model_not_found_error(exc):
                raise

    raise last_error or RuntimeError("No Bedrock model candidates could be resolved.")


async def invoke_structured(
    *,
    prompt: Any,
    output_model: type[T],
    system_prompt: str,
    model_id: str,
    tools: Optional[Sequence[Any]] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> T:
    last_error: Optional[Exception] = None
    for candidate_model_id in _candidate_model_ids(model_id):
        try:
            agent = create_agent(
                system_prompt=system_prompt,
                model_id=candidate_model_id,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = await agent.invoke_async(
                prompt,
                structured_output_model=output_model,
                structured_output_prompt=structured_output_prompt,
            )
            structured = getattr(result, "structured_output", None)
            if structured is None:
                raise RuntimeError(
                    "Structured output was not returned by the Strands agent."
                )
            return structured
        except Exception as exc:
            last_error = exc
            if not _is_model_not_found_error(exc):
                raise

    raise last_error or RuntimeError("No Bedrock model candidates could be resolved.")


def _build_image_prompt(text_prompt: str, image_path: str) -> list[dict[str, Any]]:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    subtype = (mime_type or "image/jpeg").split("/", 1)[-1]
    image_bytes = path.read_bytes()
    return [
        {"text": text_prompt},
        {"image": {"format": subtype, "source": {"bytes": image_bytes}}},
    ]


def _is_multimodal_capability_error(error: Exception) -> bool:
    text = str(error).lower()
    needles = [
        "image",
        "multimodal",
        "media",
        "unsupported",
        "does not support",
        "invalid input",
        "content block",
    ]
    return any(needle in text for needle in needles)


async def invoke_multimodal_structured(
    *,
    text_prompt: str,
    image_path: str,
    output_model: type[T],
    system_prompt: str,
    model_id: str,
    fallback_model_id: Optional[str] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> T:
    prompt = _build_image_prompt(text_prompt, image_path)
    try:
        return await invoke_structured(
            prompt=prompt,
            output_model=output_model,
            system_prompt=system_prompt,
            model_id=model_id,
            structured_output_prompt=structured_output_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        if (
            fallback_model_id
            and fallback_model_id != model_id
            and _is_multimodal_capability_error(exc)
        ):
            logger.warning(
                "Vision model %s rejected the request; retrying with fallback %s.",
                model_id,
                fallback_model_id,
            )
            return await invoke_structured(
                prompt=prompt,
                output_model=output_model,
                system_prompt=system_prompt,
                model_id=fallback_model_id,
                structured_output_prompt=structured_output_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        raise
