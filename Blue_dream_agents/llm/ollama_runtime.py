from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional, Sequence, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

try:
    from .settings import get_provider_settings
except ImportError:
    from settings import get_provider_settings


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

# Persistent HTTP client for connection pooling across Ollama calls
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a persistent httpx client for Ollama, creating one if needed."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        settings = get_provider_settings()
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
        )
    return _http_client


async def close_http_client() -> None:
    """Close the persistent HTTP client (call on shutdown)."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


def _prompt_to_text(prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt
    return json.dumps(prompt, default=str, indent=2)


def _chat_options(
    *,
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> dict[str, Any]:
    settings = get_provider_settings()
    options: dict[str, Any] = {
        "temperature": settings.default_temperature
        if temperature is None
        else temperature
    }
    options["num_predict"] = (
        settings.default_max_tokens if max_tokens is None else max_tokens
    )
    return options


async def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_provider_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    client = _get_http_client()
    response = await client.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def _image_to_base64(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image path does not exist: {image_path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _extract_message_content(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

    response = payload.get("response")
    if isinstance(response, str):
        return response.strip()

    return ""


def _strip_json_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_payload(raw_text: str) -> Any:
    cleaned = _strip_json_fences(raw_text)
    if not cleaned:
        raise ValueError("Ollama response did not contain text content.")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(cleaned[index:])
            return payload
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Ollama response did not contain valid JSON: {cleaned[:500]}")


def _format_validation_error(error: Exception, raw_text: str) -> str:
    return f"{error}; raw response: {raw_text[:500]}"


async def invoke_text(
    *,
    prompt: Any,
    system_prompt: str,
    model_id: str,
    tools: Optional[Sequence[Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    if tools:
        logger.warning("Ollama text runtime does not support Strands tools; ignoring.")

    settings = get_provider_settings()
    payload = {
        "model": model_id or settings.gemma_text_model,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _prompt_to_text(prompt)},
        ],
        "options": _chat_options(temperature=temperature, max_tokens=max_tokens),
    }
    response_payload = await _post_chat(payload)
    content = _extract_message_content(response_payload)
    if not content:
        raise RuntimeError(f"Ollama returned an empty text response: {response_payload}")
    return content


def _structured_messages(
    *,
    prompt: Any,
    output_model: type[T],
    system_prompt: str,
    structured_output_prompt: Optional[str],
    retry: bool,
) -> list[dict[str, str]]:
    schema_text = json.dumps(output_model.model_json_schema(), indent=2)
    instruction = (
        "Return only valid JSON. Do not include Markdown, prose, or code fences. "
        "The JSON must validate against this schema:\n"
        f"{schema_text}"
    )
    if structured_output_prompt:
        instruction = f"{instruction}\n\nTask-specific output instructions:\n{structured_output_prompt}"
    if retry:
        instruction = (
            "Your previous response was not valid JSON for the requested schema. "
            "Return exactly one JSON object now, with no extra text.\n\n"
            f"{instruction}"
        )

    return [
        {"role": "system", "content": f"{system_prompt}\n\n{instruction}"},
        {"role": "user", "content": _prompt_to_text(prompt)},
    ]


async def _invoke_structured_chat(
    *,
    messages: list[dict[str, Any]],
    output_model: type[T],
    model_id: str,
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> T:
    last_error: Exception | None = None
    last_raw_text = ""

    for retry in (False, True):
        retry_messages = messages
        if retry:
            retry_messages = [
                *messages[:-1],
                {
                    **messages[-1],
                    "content": (
                        "Your previous response was not valid JSON for the requested "
                        "schema. Return exactly one JSON object now, with no extra "
                        "text.\n\n"
                        f"{messages[-1].get('content', '')}"
                    ),
                },
            ]

        payload = {
            "model": model_id,
            "stream": False,
            "format": "json",
            "think": False,
            "messages": retry_messages,
            "options": _chat_options(temperature=temperature, max_tokens=max_tokens),
        }
        response_payload = await _post_chat(payload)
        raw_text = _extract_message_content(response_payload)
        last_raw_text = raw_text
        try:
            payload_json = _extract_json_payload(raw_text)
            return output_model.model_validate(payload_json)
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            logger.warning("Ollama structured parse failed: %s", exc)

    raise RuntimeError(
        "Ollama structured response could not be parsed after retry: "
        f"{_format_validation_error(last_error or RuntimeError('unknown error'), last_raw_text)}"
    )


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
    if tools:
        logger.warning("Ollama structured runtime does not support Strands tools; ignoring.")

    settings = get_provider_settings()
    messages = _structured_messages(
        prompt=prompt,
        output_model=output_model,
        system_prompt=system_prompt,
        structured_output_prompt=structured_output_prompt,
        retry=False,
    )
    return await _invoke_structured_chat(
        messages=messages,
        output_model=output_model,
        model_id=model_id or settings.gemma_text_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


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
    settings = get_provider_settings()
    model_candidates = [
        model_id or settings.gemma_vision_model,
        fallback_model_id or "",
    ]
    deduped_models: list[str] = []
    for candidate in model_candidates:
        if candidate and candidate not in deduped_models:
            deduped_models.append(candidate)

    messages = _structured_messages(
        prompt=text_prompt,
        output_model=output_model,
        system_prompt=system_prompt,
        structured_output_prompt=structured_output_prompt,
        retry=False,
    )
    messages[-1] = {
        **messages[-1],
        "images": [_image_to_base64(image_path)],
    }

    last_error: Exception | None = None
    for candidate_model in deduped_models:
        try:
            return await _invoke_structured_chat(
                messages=messages,
                output_model=output_model,
                model_id=candidate_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Ollama multimodal structured call failed with model %s: %s",
                candidate_model,
                exc,
            )

    raise RuntimeError(
        f"Ollama multimodal structured call failed for all candidates: {last_error}"
    )
