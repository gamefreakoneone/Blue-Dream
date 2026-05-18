from __future__ import annotations

import asyncio
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

try:
    from .llm.settings import load_project_env, resolve_gemini_spatial_model
    from .timezone_utils import now_local
except ImportError:
    from llm.settings import load_project_env, resolve_gemini_spatial_model
    from timezone_utils import now_local


logger = logging.getLogger(__name__)

BOUNDING_BOX_SYSTEM_INSTRUCTION = (
    "Return exactly one best bounding box as a JSON array with an optional label. "
    "Use [y1, x1, y2, x2] coordinates normalized from 0 to 1000. "
    "Do not return masks, prose, or code fences. "
    "If the object is not clearly visible, return an empty JSON array."
)


class GeminiBoundingBox(BaseModel):
    label: Optional[str] = None
    box_2d: list[int] = Field(default_factory=list, min_length=4, max_length=4)


class GeminiSpatialResult(BaseModel):
    found: bool = False
    bounding_box: Optional[GeminiBoundingBox] = None
    raw_text: str = ""
    error: Optional[str] = None


def strip_json_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_payload(raw_text: str) -> list[Any]:
    cleaned = strip_json_fences(raw_text)
    if not cleaned:
        return []

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "Gemini spatial response was not valid JSON: %s", cleaned[:200]
        )
        return []

    if isinstance(payload, dict):
        if isinstance(payload.get("boxes"), list):
            payload = payload["boxes"]
        else:
            payload = [payload]

    if not isinstance(payload, list):
        return []
    return payload


def normalize_bounding_box(candidate: Any) -> Optional[GeminiBoundingBox]:
    label: Optional[str] = None
    raw_box: Any = None

    if isinstance(candidate, dict):
        raw_box = candidate.get("box_2d")
        label = candidate.get("label")
    elif isinstance(candidate, list):
        if len(candidate) == 4:
            raw_box = candidate
        elif len(candidate) >= 5:
            raw_box = candidate[:4]
            label = candidate[4]

    if not isinstance(raw_box, list) or len(raw_box) != 4:
        return None

    coordinates: list[int] = []
    for value in raw_box:
        if isinstance(value, bool):
            return None
        try:
            coordinates.append(int(round(float(value))))
        except (TypeError, ValueError):
            return None

    y1, x1, y2, x2 = [min(1000, max(0, value)) for value in coordinates]
    if y1 > y2:
        y1, y2 = y2, y1
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 == y2 or x1 == x2:
        return None

    if label is not None:
        label = str(label).strip() or None

    return GeminiBoundingBox(label=label, box_2d=[y1, x1, y2, x2])


def parse_gemini_spatial_response(raw_text: str) -> GeminiSpatialResult:
    for candidate in _parse_json_payload(raw_text):
        bounding_box = normalize_bounding_box(candidate)
        if bounding_box is not None:
            return GeminiSpatialResult(
                found=True,
                bounding_box=bounding_box,
                raw_text=raw_text,
            )

    return GeminiSpatialResult(found=False, bounding_box=None, raw_text=raw_text)


def _candidate_model_names(model_name: str) -> list[str]:
    cleaned = model_name.strip()
    if not cleaned:
        return ["gemini-2.5-flash", "models/gemini-2.5-flash"]

    candidates = [cleaned]
    if cleaned.startswith("models/"):
        candidates.append(cleaned.split("/", 1)[1])
    else:
        candidates.append(f"models/{cleaned}")

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


@lru_cache(maxsize=1)
def _get_gemini_client() -> genai.Client:
    load_project_env()
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY for Gemini spatial localization.")
    return genai.Client(api_key=api_key)


def _build_localization_prompt(
    object_name: str,
    matched_object: Optional[str] = None,
    grounding_text: Optional[str] = None,
) -> str:
    prompt_lines = [
        f"Detect the 2D bounding box of the object '{object_name}'.",
        "Return a JSON array only, using the format "
        '[{"box_2d": [y1, x1, y2, x2], "label": "object label"}].',
        "Coordinates must be normalized from 0 to 1000 and ordered as y1, x1, y2, x2.",
        "If the object is not visible, return [].",
    ]
    if matched_object and matched_object.strip() and matched_object != object_name:
        prompt_lines.append(
            f"The room inventory matched this object as '{matched_object.strip()}'."
        )
    if grounding_text and grounding_text.strip():
        prompt_lines.append(f"Grounding context: {grounding_text.strip()}")
    return "\n".join(prompt_lines)


def _resampling_lanczos() -> int:
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def _generate_localization_response(
    image_path: str,
    object_name: str,
    matched_object: Optional[str],
    grounding_text: Optional[str],
) -> str:
    model_name = resolve_gemini_spatial_model()
    client = _get_gemini_client()
    last_error: Optional[Exception] = None
    prompt = _build_localization_prompt(
        object_name=object_name,
        matched_object=matched_object,
        grounding_text=grounding_text,
    )

    with Image.open(image_path) as source_image:
        prompt_image = source_image.convert("RGB")
    prompt_image.thumbnail((1024, 1024), _resampling_lanczos())

    for candidate_model in _candidate_model_names(model_name):
        try:
            response = client.models.generate_content(
                model=candidate_model,
                contents=[prompt, prompt_image],
                config=types.GenerateContentConfig(
                    system_instruction=BOUNDING_BOX_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return (response.text or "").strip()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Gemini spatial localization failed with model %s: %s",
                candidate_model,
                exc,
            )

    raise RuntimeError(
        f"Gemini spatial localization failed for all candidate models: {last_error}"
    )


def _normalize_to_pixels(
    box: GeminiBoundingBox, width: int, height: int
) -> tuple[int, int, int, int]:
    y1, x1, y2, x2 = box.box_2d
    max_x = max(width - 1, 0)
    max_y = max(height - 1, 0)
    left = min(max_x, max(0, round((x1 / 1000) * max_x)))
    top = min(max_y, max(0, round((y1 / 1000) * max_y)))
    right = min(max_x, max(0, round((x2 / 1000) * max_x)))
    bottom = min(max_y, max(0, round((y2 / 1000) * max_y)))
    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top
    return left, top, right, bottom


def _save_highlighted_image(
    image_path: str,
    object_name: str,
    bounding_box: GeminiBoundingBox,
    output_dir: str,
) -> str:
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        highlighted = image.convert("RGB")
        draw = ImageDraw.Draw(highlighted)
        left, top, right, bottom = _normalize_to_pixels(
            bounding_box, highlighted.width, highlighted.height
        )
        line_width = max(3, round(min(highlighted.width, highlighted.height) / 160))
        draw.rectangle((left, top, right, bottom), outline="red", width=line_width)

        timestamp = now_local().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(ch for ch in object_name if ch.isalnum()) or "object"
        saved_path = output_path / f"{safe_name}_{timestamp}.png"
        highlighted.save(saved_path, format="PNG")
        return str(saved_path)


async def localize_object_with_gemini(
    image_path: str,
    object_name: str,
    *,
    matched_object: Optional[str] = None,
    grounding_text: Optional[str] = None,
) -> GeminiSpatialResult:
    if not image_path or not os.path.exists(image_path):
        logger.warning(
            "Gemini localization skipped: image_path is empty or does not exist: %s",
            image_path,
        )
        return GeminiSpatialResult(found=False, raw_text="")

    logger.info(
        "Gemini localization request for '%s' (matched: '%s') on image: %s",
        object_name,
        matched_object or object_name,
        image_path,
    )

    try:
        raw_text = await asyncio.to_thread(
            _generate_localization_response,
            image_path,
            object_name,
            matched_object,
            grounding_text,
        )
    except Exception as exc:
        logger.warning(
            "Gemini highlight localization failed for %s: %s", object_name, exc
        )
        return GeminiSpatialResult(found=False, raw_text="", error=str(exc))

    result = parse_gemini_spatial_response(raw_text)
    if result.found:
        logger.info(
            "Gemini localization succeeded for '%s': box=%s",
            object_name,
            result.bounding_box.box_2d if result.bounding_box else "None",
        )
    else:
        logger.warning(
            "Gemini localization returned no valid bounding box for '%s'. Raw response: %s",
            object_name,
            raw_text[:300],
        )
    return result


async def render_highlighted_image(
    *,
    image_path: str,
    object_name: str,
    bounding_box: GeminiBoundingBox,
    output_dir: str = "Storage/highlighted",
) -> Optional[str]:
    try:
        return await asyncio.to_thread(
            _save_highlighted_image,
            image_path,
            object_name,
            bounding_box,
            output_dir,
        )
    except Exception as exc:
        logger.warning(
            "Gemini highlight rendering failed for %s: %s", object_name, exc
        )
        return None


async def highlight_object_with_gemini(
    image_path: str,
    object_name: str,
    *,
    matched_object: Optional[str] = None,
    grounding_text: Optional[str] = None,
    output_dir: str = "Storage/highlighted",
) -> Optional[str]:
    result = await localize_object_with_gemini(
        image_path=image_path,
        object_name=object_name,
        matched_object=matched_object,
        grounding_text=grounding_text,
    )
    if not result.found or result.bounding_box is None:
        return None

    return await render_highlighted_image(
        image_path=image_path,
        object_name=matched_object or object_name,
        bounding_box=result.bounding_box,
        output_dir=output_dir,
    )
