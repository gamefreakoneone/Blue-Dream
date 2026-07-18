from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional, Sequence, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

try:
    from ..media_paths import to_fs_path
    from .model_registry import TaskTarget, resolve
    from .settings import get_provider_settings
except ImportError:
    from media_paths import to_fs_path
    from model_registry import TaskTarget, resolve
    from settings import get_provider_settings


T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)
_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def _get_client(target: TaskTarget) -> AsyncOpenAI:
    if target.provider not in {"qwen", "openai", "ollama"}:
        raise NotImplementedError(
            f"Provider {target.provider!r} is not served by the OpenAI-compatible client."
        )
    if not target.base_url or not target.api_key:
        raise RuntimeError(
            f"Provider {target.provider!r} did not resolve an endpoint and API key."
        )

    cache_key = (target.base_url, target.api_key)
    client = _clients.get(cache_key)
    if client is None:
        client = AsyncOpenAI(
            api_key=target.api_key,
            base_url=target.base_url,
            timeout=get_provider_settings().request_timeout_seconds,
        )
        _clients[cache_key] = client
    return client


async def close_llm_clients() -> None:
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        await client.close()


def _prompt_to_text(prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt
    return json.dumps(prompt, default=str, indent=2)


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
        raise ValueError("Provider response did not contain text content.")

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

    raise ValueError(
        f"Provider response did not contain valid JSON: {cleaned[:500]}"
    )


def _structured_messages(
    *,
    prompt: Any,
    output_model: type[T],
    system_prompt: Optional[str],
    structured_output_prompt: Optional[str],
) -> list[dict[str, Any]]:
    schema_text = json.dumps(output_model.model_json_schema(), indent=2)
    instruction = (
        "Return only valid JSON. Do not include Markdown, prose, or code fences. "
        "The JSON must validate against this schema:\n"
        f"{schema_text}"
    )
    if structured_output_prompt:
        instruction += (
            "\n\nTask-specific output instructions:\n"
            f"{structured_output_prompt}"
        )

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append(
            {"role": "system", "content": f"{system_prompt}\n\n{instruction}"}
        )
    else:
        messages.append({"role": "system", "content": instruction})
    messages.append({"role": "user", "content": _prompt_to_text(prompt)})
    return messages


def _retry_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retry_messages = [dict(message) for message in messages]
    user_message = dict(retry_messages[-1])
    previous_content = user_message.get("content", "")
    if isinstance(previous_content, str):
        user_message["content"] = (
            "Your previous response was not valid JSON for the requested schema. "
            "Return exactly one JSON object now, with no extra text.\n\n"
            f"{previous_content}"
        )
    elif isinstance(previous_content, list):
        user_message["content"] = [
            {
                "type": "text",
                "text": (
                    "Your previous response was not valid JSON for the requested "
                    "schema. Return exactly one JSON object now, with no extra text."
                ),
            },
            *previous_content,
        ]
    retry_messages[-1] = user_message
    return retry_messages


def _response_format(target: TaskTarget) -> Optional[dict[str, Any]]:
    if target.supports_json_schema:
        raise NotImplementedError(
            "Strict OpenAI json_schema output is completed by spec 0012."
        )
    if target.supports_json_object:
        return {"type": "json_object"}
    return None


async def _create_chat_completion(
    *,
    target: TaskTarget,
    model_id: Optional[str],
    messages: list[dict[str, Any]],
    temperature: Optional[float],
    max_tokens: Optional[int],
    response_format: Optional[dict[str, Any]] = None,
):
    settings = get_provider_settings()
    kwargs: dict[str, Any] = {
        "model": model_id or target.model,
        "messages": messages,
        "temperature": (
            settings.default_temperature if temperature is None else temperature
        ),
        "max_tokens": settings.default_max_tokens if max_tokens is None else max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    return await _get_client(target).chat.completions.create(**kwargs)


def _completion_text(completion: Any) -> str:
    try:
        content = completion.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise ValueError("Provider response did not contain a chat message.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Provider response contained empty text content.")
    return content.strip()


async def invoke_text(
    *,
    prompt: Any,
    system_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
    tools: Optional[Sequence[Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    task: str = "text",
) -> str:
    if tools:
        logger.warning("The shared provider client currently ignores tools.")
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": _prompt_to_text(prompt)})
    completion = await _create_chat_completion(
        target=resolve(task),
        model_id=model_id,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _completion_text(completion)


async def _invoke_structured_messages(
    *,
    messages: list[dict[str, Any]],
    output_model: type[T],
    target: TaskTarget,
    model_id: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
) -> T:
    response_format = _response_format(target)
    last_error: Exception | None = None
    last_raw_text = ""

    for retry in (False, True):
        completion = await _create_chat_completion(
            target=target,
            model_id=model_id,
            messages=_retry_messages(messages) if retry else messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        raw_text = _completion_text(completion)
        last_raw_text = raw_text
        try:
            return output_model.model_validate(_extract_json_payload(raw_text))
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            logger.warning("Structured provider response failed validation: %s", exc)

    raise RuntimeError(
        "Structured provider response could not be parsed after retry: "
        f"{last_error}; raw response: {last_raw_text[:500]}"
    )


async def invoke_structured(
    *,
    prompt: Any,
    output_model: type[T],
    system_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
    tools: Optional[Sequence[Any]] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    task: str = "text",
) -> T:
    if tools:
        logger.warning("The shared provider client currently ignores tools.")
    return await _invoke_structured_messages(
        messages=_structured_messages(
            prompt=prompt,
            output_model=output_model,
            system_prompt=system_prompt,
            structured_output_prompt=structured_output_prompt,
        ),
        output_model=output_model,
        target=resolve(task),
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _image_content_part(image_path: str | Path) -> dict[str, Any]:
    resolved = to_fs_path(image_path)
    if resolved is None or not resolved.exists():
        raise FileNotFoundError(f"Image path does not exist: {image_path}")
    mime_type, _ = mimetypes.guess_type(resolved.name)
    encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type or 'image/jpeg'};base64,{encoded}"},
    }


async def invoke_multimodal_structured(
    *,
    text_prompt: str,
    image_path: str,
    output_model: type[T],
    system_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
    fallback_model_id: Optional[str] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    task: str = "vision",
) -> T:
    messages = _structured_messages(
        prompt=text_prompt,
        output_model=output_model,
        system_prompt=system_prompt,
        structured_output_prompt=structured_output_prompt,
    )
    messages[-1]["content"] = [
        {"type": "text", "text": text_prompt},
        _image_content_part(image_path),
    ]
    try:
        return await _invoke_structured_messages(
            messages=messages,
            output_model=output_model,
            target=resolve(task),
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception:
        if fallback_model_id and fallback_model_id != model_id:
            return await _invoke_structured_messages(
                messages=messages,
                output_model=output_model,
                target=resolve(task),
                model_id=fallback_model_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        raise


async def invoke_video_structured(
    *,
    output_model: type[T],
    video_url: Optional[str] = None,
    frame_paths: Optional[Sequence[str | Path]] = None,
    text_prompt: str = "Describe this room event from the supplied video evidence.",
    system_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
    structured_output_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    task: str = "video",
) -> T:
    if bool(video_url) == bool(frame_paths):
        raise ValueError("Provide exactly one of video_url or frame_paths.")

    content: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
    if video_url:
        content.append(
            {"type": "video_url", "video_url": {"url": video_url}}
        )
    else:
        content[0]["text"] = (
            "These are sequential frames from one room recording, ordered from "
            f"earliest to latest.\n\n{text_prompt}"
        )
        content.extend(_image_content_part(path) for path in frame_paths or [])

    messages = _structured_messages(
        prompt=text_prompt,
        output_model=output_model,
        system_prompt=system_prompt,
        structured_output_prompt=structured_output_prompt,
    )
    messages[-1]["content"] = content
    return await _invoke_structured_messages(
        messages=messages,
        output_model=output_model,
        target=resolve(task),
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def embed_texts(
    texts: list[str], task: str = "embedding"
) -> list[list[float]]:
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding inputs must be non-empty strings.")

    target = resolve(task)
    expected_dimension = target.embedding_dim
    batch_size = get_provider_settings().embed_batch_size
    if batch_size <= 0:
        raise RuntimeError("EMBED_BATCH_SIZE must be greater than zero.")

    embeddings: list[list[float]] = []
    client = _get_client(target)
    for start in range(0, len(texts), batch_size):
        response = await client.embeddings.create(
            model=target.model,
            input=texts[start : start + batch_size],
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        for item in ordered:
            embedding = list(item.embedding)
            if expected_dimension is not None and len(embedding) != expected_dimension:
                raise ValueError(
                    f"Embedding model {target.model!r} returned {len(embedding)} "
                    f"dimensions; expected {expected_dimension}."
                )
            embeddings.append(embedding)
    return embeddings


async def transcribe_audio(audio_path: str | Path) -> str:
    target = resolve("transcribe")
    if target.provider == "qwen":
        raise NotImplementedError("Qwen ASR is wired and live-validated in spec 0005.")
    if target.provider != "openai":
        raise NotImplementedError(
            f"Transcription is not available for provider {target.provider!r}."
        )

    resolved = to_fs_path(audio_path)
    if resolved is None or not resolved.exists():
        raise FileNotFoundError(f"Audio path does not exist: {audio_path}")
    with resolved.open("rb") as audio_file:
        transcript = await _get_client(target).audio.transcriptions.create(
            model=target.model,
            file=audio_file,
        )
    text = getattr(transcript, "text", "")
    if not isinstance(text, str):
        raise ValueError("Transcription provider did not return text.")
    return text.strip()


async def synthesize_speech(text: str) -> bytes:
    raise NotImplementedError("Speech synthesis is implemented in spec 0009.")
