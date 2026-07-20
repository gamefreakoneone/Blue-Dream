from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import with_patient_answer_context
    from .llm.settings import get_provider_settings
    from .llm.client import invoke_multimodal_structured, invoke_structured
    from .media_paths import normalize_stored_path, to_fs_path
    from .memory_schema import MemoryEvent
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.prompt_context import with_patient_answer_context
    from llm.settings import get_provider_settings
    from llm.client import invoke_multimodal_structured, invoke_structured
    from media_paths import normalize_stored_path, to_fs_path
    from memory_schema import MemoryEvent


logger = logging.getLogger(__name__)


class SafetyAssessment(BaseModel):
    warning_needed: bool = Field(
        default=False,
        description="True only when the evidence clearly supports an actionable safety warning.",
    )
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    hazard_type: str = ""
    hazard_object: str = Field(
        default="",
        description=(
            "Concise visible object responsible for an actionable warning, preferably "
            "matching a room_objects label; empty when no object can be grounded."
        ),
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    patient_message: str = ""
    detailed_explanation: str = ""
    recommended_action: str = ""
    caretaker_recommended: bool = False
    reason: str = ""


class SafetyObservationBundle(BaseModel):
    event_id: str
    room_number: int
    room_name: str
    timestamp: str
    video_description: str
    room_objects: list[str] = Field(default_factory=list)
    audio_transcript: str = ""
    danger_candidate: bool = False
    scene_end_state: str = ""
    observed_hazards: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


def safety_agent_enabled() -> bool:
    return get_provider_settings().safety_agent_enabled


def empty_safety_assessment(reason: str) -> SafetyAssessment:
    return SafetyAssessment(
        warning_needed=False,
        severity="none",
        confidence=0.0,
        reason=reason,
    )


def build_observation_bundle(event: MemoryEvent) -> SafetyObservationBundle:
    return SafetyObservationBundle(
        event_id=event.event_id,
        room_number=event.room_number,
        room_name=event.room_name,
        timestamp=event.timestamp.isoformat(),
        video_description=event.video_description,
        room_objects=event.room_objects,
        audio_transcript=event.audio_transcript,
        danger_candidate=event.danger_candidate,
        scene_end_state=event.scene_end_state,
        observed_hazards=event.observed_hazards,
        uncertainties=event.uncertainties,
    )


def _system_prompt() -> str:
    return with_patient_answer_context(
        """
        You are Memoria's safety judge. A video model has already produced factual
        observations from a Bedroom or Living Room event. Decide whether the patient
        needs an immediate, actionable warning about an environmental hazard.

        Room-agnostic scope:
        - unattended fire, smoke, gas, cooking, or dangerous heat
        - sharp objects left in unsafe locations
        - exposed electrical hazards
        - spills or obstacles that create a clear trip risk
        - open or spilled medication or household chemicals in an unsafe state

        Conservative policy:
        - Alert only when the supplied evidence clearly supports a real risk.
        - Judge unsafe state and context, not the mere presence of an ordinary object.
        - A patient using a knife normally while cutting fruit is not itself a warning. A
          sharp knife left on a bed after the patient exits is actionable.
        - Do not invent hazards, rooms, objects, or patient actions.
        - If evidence is ambiguous or only says an object exists, do not alert.
        - Do not classify falls or geofence events here. Dedicated paths send falls
          to caregivers and preserve the existing geofence behavior.
        - If a final screenshot is provided, use it as current-state evidence, but
          do not require screenshot certainty when the video evidence is strong.
        - When warning_needed is true, set hazard_object to one concise visible object
          label, preferably copied from room_objects (for example "knife" or
          "electrical cord"). Do not include its location or a full sentence. Use an
          empty string when no object can be grounded.
        - Patient-facing text must be short, calm, direct, and tell the patient what
          to do now.
        """
    )


def _structured_prompt(bundle: SafetyObservationBundle) -> dict[str, Any]:
    return {
        "task": "Decide whether this monitored home event requires an urgent patient safety warning.",
        "observation_bundle": bundle.model_dump(mode="json"),
        "output_guidance": {
            "warning_needed": "true only for clear actionable danger",
            "severity": "none for no alert, low for store-only concern, medium/high/critical for actionable alerts",
            "hazard_type": "for example sharp_object_left_unsafe, unattended_cooking, exposed_electrical, spill_trip_hazard, accessible_chemical, or empty",
            "hazard_object": "one concise visible object label, preferably copied from room_objects; empty if warning_needed is false or no object is groundable",
            "patient_message": "one short notification body if warning_needed is true",
            "detailed_explanation": "plain explanation for the mobile alert detail screen",
            "recommended_action": "specific patient action such as move_knife_to_safe_place, turn_off_stove, avoid_spill, or call_for_help",
        },
    }


async def assess_event_safety(event: MemoryEvent) -> SafetyAssessment:
    if not safety_agent_enabled():
        return empty_safety_assessment("Safety agent disabled by SAFETY_AGENT_ENABLED.")

    bundle = build_observation_bundle(event)
    if not bundle.danger_candidate and not bundle.observed_hazards:
        return empty_safety_assessment("No danger candidate or observed hazards from video analysis.")

    registry = get_model_registry()
    prompt = _structured_prompt(bundle)
    structured_output_prompt = (
        "Return a safety decision for this one event. Use warning_needed=false and "
        "severity='none' when the evidence is only uncertain."
    )

    screenshot_path = to_fs_path(normalize_stored_path(event.screenshot_path))
    try:
        if screenshot_path is not None and screenshot_path.exists():
            text_prompt = json.dumps(prompt, default=str, indent=2)
            return await invoke_multimodal_structured(
                text_prompt=text_prompt,
                image_path=str(screenshot_path),
                output_model=SafetyAssessment,
                system_prompt=_system_prompt(),
                model_id=registry.vision,
                fallback_model_id=registry.vision_fallback,
                structured_output_prompt=structured_output_prompt,
                temperature=0.0,
                max_tokens=900,
            )

        return await invoke_structured(
            prompt=prompt,
            output_model=SafetyAssessment,
            system_prompt=_system_prompt(),
            model_id=registry.synthesis,
            structured_output_prompt=structured_output_prompt,
            temperature=0.0,
            max_tokens=900,
        )
    except Exception:
        logger.exception("Safety assessment failed for event %s", event.event_id)
        raise
