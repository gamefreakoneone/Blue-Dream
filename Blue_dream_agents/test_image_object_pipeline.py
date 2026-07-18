from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

try:
    from .gemini_spatial import (
        GeminiSpatialResult,
        localize_object_with_gemini,
        render_highlighted_image,
    )
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_cctv_context,
    )
    from .llm.client import invoke_multimodal_structured
except ImportError:
    from gemini_spatial import (
        GeminiSpatialResult,
        localize_object_with_gemini,
        render_highlighted_image,
    )
    from llm.model_registry import get_model_registry
    from llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_cctv_context,
    )
    from llm.client import invoke_multimodal_structured


class ObjectVisionCheck(BaseModel):
    found: bool = False
    description: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    matched_object: Optional[str] = None


class ImageObjectPipelineResult(BaseModel):
    image_path: str
    object_name: str
    vision_model: str
    vision_result: ObjectVisionCheck
    gemini_spatial_result: Optional[GeminiSpatialResult] = None
    highlighted_image_path: Optional[str] = Field(default=None)


async def run_image_object_pipeline(
    *,
    image_path: str,
    object_name: str,
    output_dir: str,
) -> ImageObjectPipelineResult:
    source_image = Path(image_path)
    if not source_image.exists():
        raise FileNotFoundError(f"Image does not exist: {image_path}")

    registry = get_model_registry()
    vision_result = await invoke_multimodal_structured(
        text_prompt=with_monitoring_evidence_context(
            f"Target object: {object_name}\n"
            "Current image source: a fixed room CCTV snapshot, not a first-person view.\n"
            "Decide whether the image visibly contains the target object or a clear "
            "synonym. If found, describe where it is in one short grounded sentence "
            "and provide the matched object string when a synonym or specific variant "
            "is visible."
        ),
        image_path=str(source_image),
        output_model=ObjectVisionCheck,
        system_prompt=with_patient_cctv_context(
            "You inspect room images for a lost-object assistant. Only mark found "
            "true when the object is visibly present in the current image."
        ),
        model_id=registry.vision,
        fallback_model_id=registry.vision_fallback,
        structured_output_prompt=(
            "Return found, description, confidence, and optional matched_object. "
            "If the object is not visible, return found=false."
        ),
        max_tokens=300,
    )

    highlighted_image_path: Optional[str] = None
    gemini_spatial_result: Optional[GeminiSpatialResult] = None
    if vision_result.found:
        gemini_spatial_result = await localize_object_with_gemini(
            image_path=str(source_image),
            object_name=object_name,
            matched_object=vision_result.matched_object,
            grounding_text=vision_result.description,
        )
        if gemini_spatial_result.found and gemini_spatial_result.bounding_box:
            highlighted_image_path = await render_highlighted_image(
                image_path=str(source_image),
                object_name=vision_result.matched_object or object_name,
                bounding_box=gemini_spatial_result.bounding_box,
                output_dir=output_dir,
            )

    return ImageObjectPipelineResult(
        image_path=str(source_image),
        object_name=object_name,
        vision_model=registry.vision,
        vision_result=vision_result,
        gemini_spatial_result=gemini_spatial_result,
        highlighted_image_path=highlighted_image_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a single-image object pipeline test: Gemma visibility check plus "
            "Gemini spatial localization/highlight rendering."
        )
    )
    parser.add_argument(
        "--image",
        default=r"Storage\screenshots\camera_1\camera_1_2026-01-15_16-20-31.jpg",
        help="Path to the screenshot to inspect.",
    )
    parser.add_argument(
        "--object",
        default="black headphones",
        help="Object to find in the screenshot.",
    )
    parser.add_argument(
        "--output-dir",
        default=r"Storage\highlighted\pipeline_tests",
        help="Directory where highlighted images should be written.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    result = await run_image_object_pipeline(
        image_path=args.image,
        object_name=args.object,
        output_dir=args.output_dir,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
