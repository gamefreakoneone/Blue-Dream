from __future__ import annotations

import asyncio
import datetime
import logging
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from bson import ObjectId
from pymongo import ReturnDocument

try:
    from .db_client import (
        ensure_alert_indexes as ensure_alert_indexes_in_db,
        get_devices_collection,
        get_geofence_collection,
        get_safety_alerts_collection,
    )
    from .gemini_spatial import highlight_object_with_gemini
    from .llm.settings import get_provider_settings
    from .memory_schema import MemoryEvent
    from .safety_agent import SafetyAssessment
    from .timezone_utils import now_local
except ImportError:
    from db_client import (
        ensure_alert_indexes as ensure_alert_indexes_in_db,
        get_devices_collection,
        get_geofence_collection,
        get_safety_alerts_collection,
    )
    from gemini_spatial import highlight_object_with_gemini
    from llm.settings import get_provider_settings
    from memory_schema import MemoryEvent
    from safety_agent import SafetyAssessment
    from timezone_utils import now_local


logger = logging.getLogger(__name__)

SEVERITY_RANK = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

KITCHEN_HAZARD_TERMS = (
    "stove",
    "burner",
    "pot",
    "pan",
    "smoke",
    "flame",
    "fire",
    "kettle",
    "boiling",
)

_alert_indexes_ready = False
_alert_indexes_lock = asyncio.Lock()


async def initialize_alert_indexes() -> None:
    """Create alert indexes once in this process, retrying after failures."""

    global _alert_indexes_ready
    if _alert_indexes_ready:
        return

    async with _alert_indexes_lock:
        if _alert_indexes_ready:
            return
        await ensure_alert_indexes_in_db()
        _alert_indexes_ready = True


def _severity_allows_alert(severity: str, min_severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 2)


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def serialize_alert(doc: dict[str, Any]) -> dict[str, Any]:
    serialized = _json_safe(doc)
    serialized.pop("_id", None)
    return serialized


def _combined_hazard_text(event: MemoryEvent, assessment: SafetyAssessment) -> str:
    parts = [
        assessment.hazard_type,
        assessment.recommended_action,
        assessment.patient_message,
        assessment.detailed_explanation,
        assessment.reason,
        event.video_description,
        event.scene_end_state,
        " ".join(event.room_objects),
        " ".join(event.observed_hazards),
        " ".join(event.uncertainties),
    ]
    return " ".join(part for part in parts if part).lower()


def choose_highlight_target(
    event: MemoryEvent, assessment: SafetyAssessment
) -> Optional[str]:
    """Pick one visible hazard target to highlight in the alert detail image."""

    text = _combined_hazard_text(event, assessment)
    if not text:
        return None

    for term in KITCHEN_HAZARD_TERMS:
        if term in text:
            if term == "boiling":
                return "pot"
            if term == "fire":
                return "flame"
            return term

    hazard_type = assessment.hazard_type.lower()
    if "cooking" in hazard_type or "stove" in hazard_type:
        return "stove"
    if "smoke" in hazard_type:
        return "smoke"
    if "flame" in hazard_type or "fire" in hazard_type:
        return "flame"
    return None


async def build_alert_image_fields(
    event: MemoryEvent, assessment: SafetyAssessment
) -> dict[str, Any]:
    original_image_path = event.screenshot_path or ""
    if not original_image_path:
        return {
            "image_path": "",
            "original_image_path": "",
            "highlight_target": None,
            "highlight_status": "unavailable",
        }

    if not Path(original_image_path).exists():
        return {
            "image_path": original_image_path,
            "original_image_path": original_image_path,
            "highlight_target": None,
            "highlight_status": "unavailable",
        }

    highlight_target = choose_highlight_target(event, assessment)
    if not highlight_target:
        return {
            "image_path": original_image_path,
            "original_image_path": original_image_path,
            "highlight_target": None,
            "highlight_status": "fallback_original",
        }

    grounding_text = (
        assessment.detailed_explanation
        or assessment.reason
        or event.scene_end_state
        or event.video_description
    )
    try:
        highlighted_path = await highlight_object_with_gemini(
            image_path=original_image_path,
            object_name=highlight_target,
            matched_object=highlight_target,
            grounding_text=grounding_text,
            output_dir="Storage/highlighted",
        )
    except Exception as exc:
        logger.warning(
            "Alert image highlighting failed for event %s target %s: %s",
            event.event_id,
            highlight_target,
            exc,
        )
        highlighted_path = None

    if highlighted_path:
        return {
            "image_path": highlighted_path,
            "original_image_path": original_image_path,
            "highlight_target": highlight_target,
            "highlight_status": "generated",
        }

    return {
        "image_path": original_image_path,
        "original_image_path": original_image_path,
        "highlight_target": highlight_target,
        "highlight_status": "fallback_original",
    }


async def register_device(
    *,
    device_id: str,
    platform: str,
    push_provider: str,
    push_token: str,
    role: str = "patient",
) -> dict[str, Any]:
    await initialize_alert_indexes()
    now = now_local()
    document = {
        "device_id": device_id,
        "platform": platform,
        "push_provider": push_provider,
        "push_token": push_token,
        "role": role,
        "enabled": True,
        "updated_at": now,
    }
    await get_devices_collection().update_one(
        {"device_id": device_id},
        {
            "$set": document,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return _json_safe(document)


async def list_patient_alerts(status: Optional[str] = "open") -> list[dict[str, Any]]:
    await initialize_alert_indexes()
    query: dict[str, Any] = {"target_role": "patient"}
    if status and status != "all":
        query["status"] = status
    cursor = (
        get_safety_alerts_collection()
        .find(query)
        .sort("created_at", -1)
        .limit(50)
    )
    return [serialize_alert(doc) async for doc in cursor]


async def get_alert(alert_id: str) -> Optional[dict[str, Any]]:
    await initialize_alert_indexes()
    doc = await get_safety_alerts_collection().find_one({"alert_id": alert_id})
    return serialize_alert(doc) if doc else None


async def acknowledge_alert(alert_id: str, action: str) -> Optional[dict[str, Any]]:
    await initialize_alert_indexes()
    now = now_local()
    result = await get_safety_alerts_collection().find_one_and_update(
        {"alert_id": alert_id},
        {
            "$set": {
                "status": "acknowledged",
                "ack_action": action,
                "acknowledged_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return serialize_alert(result) if result else None


async def build_alert_document(
    event: MemoryEvent, assessment: SafetyAssessment
) -> dict[str, Any]:
    now = now_local()
    alert_id = str(ObjectId())
    title = "Memoria safety alert"
    if assessment.hazard_type:
        title = f"Memoria: {assessment.hazard_type.replace('_', ' ').title()}"
    image_fields = await build_alert_image_fields(event, assessment)

    return {
        "_id": ObjectId(alert_id),
        "alert_id": alert_id,
        "event_id": event.event_id,
        "alert_type": "safety",
        "hazard_type": assessment.hazard_type or "unknown",
        "severity": assessment.severity,
        "confidence": assessment.confidence,
        "target_role": "patient",
        "title": title,
        "body": assessment.patient_message,
        "message": assessment.patient_message,
        "detailed_explanation": assessment.detailed_explanation,
        "recommended_action": assessment.recommended_action,
        "caretaker_recommended": assessment.caretaker_recommended,
        "room_number": event.room_number,
        "room_name": event.room_name,
        **image_fields,
        "status": "open",
        "delivery_status": "pending",
        "deep_link": f"memoria://alerts/{alert_id}",
        "created_at": now,
        "updated_at": now,
    }


async def create_alert_for_safety_assessment(
    event: MemoryEvent, assessment: SafetyAssessment
) -> Optional[dict[str, Any]]:
    settings = get_provider_settings()
    if not assessment.warning_needed:
        return None
    if not _severity_allows_alert(assessment.severity, settings.safety_alert_min_severity):
        return None

    await initialize_alert_indexes()
    alert = await build_alert_document(event, assessment)
    await get_safety_alerts_collection().insert_one(alert)
    try:
        delivery_status = await deliver_patient_alert(alert)
    except Exception as exc:
        logger.warning("Patient alert delivery failed for %s: %s", alert["alert_id"], exc)
        delivery_status = {"status": "failed", "error": str(exc)}

    await get_safety_alerts_collection().update_one(
        {"alert_id": alert["alert_id"]},
        {
            "$set": {
                "delivery_status": delivery_status.get("status", "unknown"),
                "delivery_details": delivery_status,
                "updated_at": now_local(),
            }
        },
    )
    alert.update(
        {
            "delivery_status": delivery_status.get("status", "unknown"),
            "delivery_details": delivery_status,
        }
    )
    return serialize_alert(alert)


async def _get_fcm_access_token(credentials_path: str) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("google-auth is required for FCM HTTP v1 delivery.") from exc

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    credentials.refresh(Request())
    return credentials.token


async def _send_fcm_message(push_token: str, alert: dict[str, Any]) -> dict[str, Any]:
    settings = get_provider_settings()
    if not settings.firebase_project_id:
        return {"status": "not_configured", "reason": "Missing FIREBASE_PROJECT_ID"}
    if not settings.firebase_credentials_path:
        return {"status": "not_configured", "reason": "Missing FIREBASE_CREDENTIALS_PATH"}

    credentials_path = Path(settings.firebase_credentials_path)
    if not credentials_path.exists():
        return {
            "status": "not_configured",
            "reason": f"Firebase credentials file not found: {credentials_path}",
        }

    token = await _get_fcm_access_token(str(credentials_path))
    url = (
        "https://fcm.googleapis.com/v1/projects/"
        f"{settings.firebase_project_id}/messages:send"
    )
    payload = {
        "message": {
            "token": push_token,
            "notification": {
                "title": alert["title"],
                "body": alert["body"],
            },
            "data": {
                "alert_id": alert["alert_id"],
                "hazard_type": alert["hazard_type"],
                "severity": alert["severity"],
                "title": alert["title"],
                "body": alert["body"],
                "deep_link": alert["deep_link"],
            },
            "android": {
                "priority": "HIGH",
                "notification": {
                    "channel_id": "urgent_alerts",
                    "click_action": "OPEN_ALERT",
                },
            },
        }
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        return {"status": "sent", "response": response.json()}


async def deliver_patient_alert(alert: dict[str, Any]) -> dict[str, Any]:
    await initialize_alert_indexes()
    cursor = get_devices_collection().find(
        {
            "role": "patient",
            "enabled": True,
            "push_provider": "fcm",
            "push_token": {"$ne": ""},
        }
    )
    devices = [doc async for doc in cursor]
    if not devices:
        return {"status": "no_devices"}

    results = []
    sent_count = 0
    for device in devices:
        try:
            result = await _send_fcm_message(device["push_token"], alert)
            if result.get("status") == "sent":
                sent_count += 1
            results.append({"device_id": device.get("device_id"), **result})
        except Exception as exc:
            results.append(
                {
                    "device_id": device.get("device_id"),
                    "status": "failed",
                    "error": str(exc),
                }
            )

    if sent_count:
        return {"status": "sent", "sent_count": sent_count, "results": results}
    if all(item.get("status") == "not_configured" for item in results):
        return {"status": "not_configured", "results": results}
    return {"status": "failed", "results": results}


async def get_current_geofence() -> dict[str, Any]:
    await initialize_alert_indexes()
    settings = get_provider_settings()
    doc = await get_geofence_collection().find_one({"config_id": "default"})
    if doc:
        return _json_safe(doc)
    return {
        "config_id": "default",
        "home_lat": settings.patient_home_lat,
        "home_lng": settings.patient_home_lng,
        "radius_meters": settings.patient_geofence_radius_meters,
        "source": "env_defaults",
    }


async def update_current_geofence(
    *, home_lat: float, home_lng: float, radius_meters: float
) -> dict[str, Any]:
    await initialize_alert_indexes()
    now = now_local()
    doc = {
        "config_id": "default",
        "home_lat": home_lat,
        "home_lng": home_lng,
        "radius_meters": radius_meters,
        "updated_at": now,
    }
    await get_geofence_collection().update_one(
        {"config_id": "default"},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return _json_safe(doc)


async def record_geofence_event(
    *,
    event_type: Literal["exit", "enter"],
    latitude: float,
    longitude: float,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
    await initialize_alert_indexes()
    now = now_local()
    alert_id = str(ObjectId())
    status = "open" if event_type == "exit" else "resolved"
    doc = {
        "_id": ObjectId(alert_id),
        "alert_id": alert_id,
        "event_id": "",
        "alert_type": "geofence_exit" if event_type == "exit" else "geofence_enter",
        "hazard_type": "geofence_exit" if event_type == "exit" else "geofence_enter",
        "severity": "medium" if event_type == "exit" else "low",
        "confidence": 1.0,
        "target_role": "patient",
        "title": "Memoria location check",
        "body": "You seem to be outside your safe area. Are you okay?",
        "message": "You seem to be outside your safe area. Are you okay?",
        "detailed_explanation": (
            "Your phone reported that you moved outside the configured safe area."
        ),
        "recommended_action": "confirm_ok_or_guide_home",
        "caretaker_recommended": event_type == "exit",
        "location": {"latitude": latitude, "longitude": longitude},
        "device_id": device_id,
        "status": status,
        "delivery_status": "pending",
        "deep_link": f"memoria://alerts/{alert_id}",
        "created_at": now,
        "updated_at": now,
    }
    await get_safety_alerts_collection().insert_one(doc)
    if event_type == "exit":
        delivery_status = await deliver_patient_alert(doc)
        await get_safety_alerts_collection().update_one(
            {"alert_id": alert_id},
            {"$set": {"delivery_status": delivery_status.get("status", "unknown")}},
        )
        doc["delivery_status"] = delivery_status.get("status", "unknown")
        doc["delivery_details"] = delivery_status
    return serialize_alert(doc)
