from __future__ import annotations

import json
import logging
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from .bedrock_client import get_bedrock_boto_config
    from .settings import get_provider_settings
except ImportError:
    from bedrock_client import get_bedrock_boto_config
    from settings import get_provider_settings


logger = logging.getLogger(__name__)
EmbeddingPurpose = Literal["document", "query"]


def _build_payload_candidates(
    text: str, purpose: EmbeddingPurpose, embedding_dimension: int
) -> list[dict[str, Any]]:
    purpose_name = "TEXT_RETRIEVAL" if purpose == "query" else "GENERIC_INDEX"
    base_payload = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": purpose_name,
            "embeddingDimension": embedding_dimension,
            "text": {
                "truncationMode": "END",
                "value": text,
            },
        },
    }
    return [
        {"schemaVersion": "nova-multimodal-embed-v1", **base_payload},
        base_payload,
    ]


def _extract_embedding(payload: dict[str, Any]) -> list[float] | None:
    candidates: list[Any] = [
        payload.get("embedding"),
        payload.get("vector"),
    ]
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        candidates.append(embeddings[0])
        if isinstance(embeddings[0], dict):
            candidates.append(embeddings[0].get("embedding"))
            candidates.append(embeddings[0].get("vector"))

    for candidate in candidates:
        if isinstance(candidate, list) and candidate and all(
            isinstance(value, (int, float)) for value in candidate
        ):
            return [float(value) for value in candidate]
    return None


def _invoke_with_boto3(body: dict[str, Any]) -> dict[str, Any]:
    if boto3 is None:
        raise RuntimeError(
            "boto3 is not installed. Install project dependencies before using "
            "Nova embeddings."
        )
    settings = get_provider_settings()
    client = boto3.client(
        "bedrock-runtime",
        region_name=settings.bedrock_region,
        config=get_bedrock_boto_config(),
    )
    response = client.invoke_model(
        modelId=settings.nova_embedding_model,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    return json.loads(response["body"].read())


def _invoke_with_bearer_token(body: dict[str, Any]) -> dict[str, Any]:
    settings = get_provider_settings()
    if not settings.aws_bearer_token_bedrock:
        raise RuntimeError("Missing AWS_BEARER_TOKEN_BEDROCK for Bedrock API-key auth.")

    encoded_model_id = quote(settings.nova_embedding_model, safe="")
    url = (
        f"https://bedrock-runtime.{settings.bedrock_region}.amazonaws.com/model/"
        f"{encoded_model_id}/invoke"
    )
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.aws_bearer_token_bedrock}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Bedrock API-key invoke failed with HTTP {exc.code}: {error_body}"
        ) from exc


def _invoke_with_ollama(text: str) -> dict[str, Any]:
    settings = get_provider_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embed"
    request = Request(
        url,
        data=json.dumps(
            {
                "model": settings.local_embedding_model,
                "input": text,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404 or "not found" in error_body.lower():
            raise RuntimeError(
                f"Ollama embedding model '{settings.local_embedding_model}' is not "
                f"available. Run `ollama pull {settings.local_embedding_model}`."
            ) from exc
        raise RuntimeError(
            f"Ollama embedding request failed with HTTP {exc.code}: {error_body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Unable to reach Ollama at {settings.ollama_base_url}: {exc}"
        ) from exc


def _validate_embedding_dimension(
    embedding: list[float], embedding_dimension: int, model_name: str
) -> list[float]:
    if len(embedding) != embedding_dimension:
        raise RuntimeError(
            f"Embedding model {model_name} returned {len(embedding)} dimensions; "
            f"expected {embedding_dimension}. Update CHROMA_EMBEDDING_DIMENSION "
            "or rebuild the index with the matching model."
        )
    return embedding


def embed_text(
    text: str,
    purpose: EmbeddingPurpose = "document",
    embedding_dimension: int | None = None,
) -> list[float]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Cannot embed an empty string.")

    settings = get_provider_settings()
    expected_dimension = embedding_dimension or settings.chroma_embedding_dimension
    if settings.embedding_provider == "ollama":
        payload = _invoke_with_ollama(cleaned_text)
        embedding = _extract_embedding(payload)
        if not embedding:
            raise RuntimeError(
                "Ollama embedding response did not contain a supported vector "
                f"payload: {payload}"
            )
        return _validate_embedding_dimension(
            embedding, expected_dimension, settings.local_embedding_model
        )

    if settings.bedrock_auth_mode == "aws_credentials":
        invoke = _invoke_with_boto3
    elif settings.bedrock_auth_mode == "api_key":
        invoke = _invoke_with_bearer_token
    else:
        raise RuntimeError(
            "Bedrock embedding credentials are not configured. Set "
            "EMBEDDING_PROVIDER=ollama to use local embeddings, or configure "
            "AWS credentials/API key for legacy Nova embeddings."
        )

    last_error: Exception | None = None
    for candidate in _build_payload_candidates(cleaned_text, purpose, expected_dimension):
        try:
            payload = invoke(candidate)
            embedding = _extract_embedding(payload)
            if embedding:
                return _validate_embedding_dimension(
                    embedding, expected_dimension, settings.nova_embedding_model
                )
            raise RuntimeError(
                f"Embedding response did not contain a supported vector payload: {payload}"
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Embedding attempt failed for payload %s: %s",
                json.dumps(candidate, default=str),
                exc,
            )

    raise RuntimeError(
        f"Unable to generate embeddings with model {settings.nova_embedding_model}: "
        f"{last_error}"
    )


def run_embedding_smoke_test(
    text: str = "What was I talking about earlier?",
) -> dict[str, Any]:
    settings = get_provider_settings()
    embedding = embed_text(
        text,
        purpose="query",
        embedding_dimension=settings.chroma_embedding_dimension,
    )
    model = (
        settings.local_embedding_model
        if settings.embedding_provider == "ollama"
        else settings.nova_embedding_model
    )
    return {
        "provider": settings.embedding_provider,
        "model": model,
        "dimension": len(embedding),
        "head": embedding[:8],
    }


if __name__ == "__main__":
    print(run_embedding_smoke_test())
