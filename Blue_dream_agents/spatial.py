"""Provider-neutral object localization and highlight rendering."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

from PIL import Image
from pydantic import BaseModel, Field

try:
    from .gemini_spatial import (
        GeminiBoundingBox,
        highlight_object_with_gemini,
        render_highlighted_image,
    )
    from .llm.client import invoke_multimodal_structured
    from .llm.settings import get_provider_settings
except ImportError:
    from gemini_spatial import (
        GeminiBoundingBox,
        highlight_object_with_gemini,
        render_highlighted_image,
    )
    from llm.client import invoke_multimodal_structured
    from llm.settings import get_provider_settings


logger = logging.getLogger(__name__)
CoordinateConvention = Literal["normalized_0_1000", "absolute_pixels"]


class QwenSpatialPayload(BaseModel):
    bbox_2d: list[float] = Field(default_factory=list, min_length=4, max_length=4)
    label: str = ""


def qwen_box_to_gemini(
    coordinates: list[float],
    *,
    image_width: int,
    image_height: int,
    convention: CoordinateConvention = "normalized_0_1000",
) -> GeminiBoundingBox:
    """Convert Qwen's [x1,y1,x2,y2] box to Gemini's normalized y/x box."""

    if len(coordinates) != 4 or image_width <= 0 or image_height <= 0:
        raise ValueError("A four-coordinate box and positive image dimensions are required.")
    x1, y1, x2, y2 = (float(value) for value in coordinates)
    if convention == "absolute_pixels":
        x1, x2 = x1 * 1000 / image_width, x2 * 1000 / image_width
        y1, y2 = y1 * 1000 / image_height, y2 * 1000 / image_height
    x1, x2 = sorted((max(0, min(1000, x1)), max(0, min(1000, x2))))
    y1, y2 = sorted((max(0, min(1000, y1)), max(0, min(1000, y2))))
    if x1 == x2 or y1 == y2:
        raise ValueError("The localized bounding box has zero area.")
    return GeminiBoundingBox(
        box_2d=[round(y1), round(x1), round(y2), round(x2)]
    )


async def _highlight_with_qwen(
    image_path: str,
    object_name: str,
    *,
    matched_object: Optional[str],
    grounding_text: Optional[str],
    output_dir: str | Path,
) -> Optional[str]:
    prompt = (
        f"Locate the visible object '{matched_object or object_name}'. "
        "Return JSON only with bbox_2d as [x1,y1,x2,y2] normalized from 0 to "
        "1000 and a short label. Return an empty bbox_2d if it is not visible."
    )
    if grounding_text:
        prompt += f" Scene context: {grounding_text}"
    payload = await invoke_multimodal_structured(
        text_prompt=prompt,
        image_path=image_path,
        output_model=QwenSpatialPayload,
        task="spatial",
    )
    if len(payload.bbox_2d) != 4:
        return None
    with Image.open(image_path) as image:
        box = qwen_box_to_gemini(
            payload.bbox_2d,
            image_width=image.width,
            image_height=image.height,
        )
    box.label = payload.label or matched_object or object_name
    return await render_highlighted_image(
        image_path=image_path,
        object_name=matched_object or object_name,
        bounding_box=box,
        output_dir=output_dir,
    )


async def highlight_object(
    image_path: str,
    object_name: str,
    *,
    matched_object: Optional[str] = None,
    grounding_text: Optional[str] = None,
    output_dir: str | Path = "Storage/highlighted",
) -> Optional[str]:
    """Highlight through the configured provider, falling back to Gemini."""

    if get_provider_settings().spatial_provider == "gemini":
        return await highlight_object_with_gemini(
            image_path=image_path,
            object_name=object_name,
            matched_object=matched_object,
            grounding_text=grounding_text,
            output_dir=output_dir,
        )
    try:
        result = await _highlight_with_qwen(
            image_path,
            object_name,
            matched_object=matched_object,
            grounding_text=grounding_text,
            output_dir=output_dir,
        )
        if result:
            return result
        raise RuntimeError("Qwen returned no usable bounding box.")
    except Exception as exc:
        logger.warning("Qwen spatial localization failed; trying Gemini: %s", exc)
        return await highlight_object_with_gemini(
            image_path=image_path,
            object_name=object_name,
            matched_object=matched_object,
            grounding_text=grounding_text,
            output_dir=output_dir,
        )
