from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import logging
import os
import re
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
    from .spatial import highlight_object
    from .llm.settings import get_provider_settings
    from .media_paths import (
        normalize_stored_path,
        resolve_output_dir,
        to_fs_path,
        to_stored_path,
        to_url_path,
    )
    from .memory_schema import MemoryEvent
    from .proactive_service import create_message as create_proactive_message
    from .safety_agent import SafetyAssessment
    from .timezone_utils import now_local
except ImportError:
    from db_client import (
        ensure_alert_indexes as ensure_alert_indexes_in_db,
        get_devices_collection,
        get_geofence_collection,
        get_safety_alerts_collection,
    )
    from spatial import highlight_object
    from llm.settings import get_provider_settings
    from media_paths import (
        normalize_stored_path,
        resolve_output_dir,
        to_fs_path,
        to_stored_path,
        to_url_path,
    )
    from memory_schema import MemoryEvent
    from proactive_service import create_message as create_proactive_message
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

LEGACY_HAZARD_TARGET_ALIASES = (
    ("knife", "knife"),
    ("blade", "knife"),
    ("scissors", "scissors"),
    ("stove", "stove"),
    ("burner", "burner"),
    ("pot", "pot"),
    ("pan", "pan"),
    ("smoke", "smoke"),
    ("flame", "flame"),
    ("fire", "flame"),
    ("kettle", "kettle"),
    ("boiling", "pot"),
    ("electrical cord", "electrical cord"),
    ("power cord", "power cord"),
    ("spill", "spill"),
    ("medication bottle", "medication bottle"),
    ("pill bottle", "pill bottle"),
    ("chemical container", "chemical container"),
)
NULL_HAZARD_TARGETS = frozenset(
    {"none", "null", "n/a", "na", "unknown", "not applicable", "no visible object"}
)
NON_PATIENT_SAFETY_HAZARD_TYPES = frozenset(
    {"fall", "possible_fall", "patient_fall", "geofence_exit", "geofence_enter"}
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


def is_patient_actionable_safety_assessment(
    assessment: SafetyAssessment, min_severity: str
) -> bool:
    """Apply the production patient-alert gate without performing side effects."""

    if assessment.hazard_type.strip().casefold() in NON_PATIENT_SAFETY_HAZARD_TYPES:
        return False
    return assessment.warning_needed and _severity_allows_alert(
        assessment.severity, min_severity
    )


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
    for field in ("image_path", "original_image_path"):
        if field in serialized:
            serialized[field] = to_url_path(serialized[field])
    return serialized


def _joined_text(parts: list[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip()).casefold()


def _hazard_specific_text(event: MemoryEvent, assessment: SafetyAssessment) -> str:
    parts = [
        assessment.hazard_type,
        assessment.recommended_action,
        assessment.patient_message,
        assessment.detailed_explanation,
        assessment.reason,
        " ".join(event.observed_hazards),
    ]
    return _joined_text(parts)


def _combined_hazard_text(event: MemoryEvent, assessment: SafetyAssessment) -> str:
    return _joined_text(
        [
            _hazard_specific_text(event, assessment),
            event.scene_end_state,
            event.video_description,
        ]
    )


def _normalize_highlight_target(value: str | None) -> Optional[str]:
    normalized = " ".join(str(value or "").split()).strip(" \t\r\n.,;:")
    if not normalized or normalized.casefold() in NULL_HAZARD_TARGETS:
        return None
    return normalized


def _contains_whole_phrase(text: str, phrase: str) -> bool:
    words = re.findall(r"\w+", phrase.casefold())
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
    return re.search(pattern, text.casefold()) is not None


def _legacy_alias_target(text: str) -> Optional[str]:
    for phrase, target in LEGACY_HAZARD_TARGET_ALIASES:
        if _contains_whole_phrase(text, phrase):
            return target
    return None


def _room_object_matches_text(room_object: str, text: str) -> bool:
    if _contains_whole_phrase(text, room_object):
        return True
    words = re.findall(r"\w+", room_object.casefold())
    return len(words) > 1 and len(words[-1]) >= 3 and _contains_whole_phrase(
        text, words[-1]
    )


def _object_matches_alias(room_object: str, alias_target: str) -> bool:
    return _contains_whole_phrase(room_object, alias_target) or _contains_whole_phrase(
        alias_target, room_object
    )


def choose_highlight_target(
    event: MemoryEvent, assessment: SafetyAssessment
) -> Optional[str]:
    """Pick one visible hazard target to highlight in the alert detail image."""

    explicit_target = _normalize_highlight_target(assessment.hazard_object)
    if explicit_target:
        return explicit_target

    specific_text = _hazard_specific_text(event, assessment)
    combined_text = _combined_hazard_text(event, assessment)
    alias_target = _legacy_alias_target(combined_text)

    matches: list[str] = []
    seen: set[str] = set()
    for value in event.room_objects:
        candidate = _normalize_highlight_target(value)
        if not candidate or candidate.casefold() in seen:
            continue
        if _room_object_matches_text(candidate, specific_text):
            seen.add(candidate.casefold())
            matches.append(candidate)

    if alias_target:
        alias_matches = [
            candidate
            for candidate in matches
            if _object_matches_alias(candidate, alias_target)
        ]
        if len(alias_matches) == 1:
            return alias_matches[0]
    elif len(matches) == 1:
        return matches[0]

    return alias_target


def _alert_grounding_text(event: MemoryEvent, assessment: SafetyAssessment) -> str:
    parts = [
        assessment.detailed_explanation,
        " ".join(event.observed_hazards),
        event.scene_end_state,
    ]
    grounding_text = " ".join(part.strip() for part in parts if part and part.strip())
    return grounding_text or assessment.reason or event.video_description


async def build_alert_image_fields(
    event: MemoryEvent, assessment: SafetyAssessment
) -> dict[str, Any]:
    original_image_path = normalize_stored_path(event.screenshot_path) or ""
    if not original_image_path:
        return {
            "image_path": "",
            "original_image_path": "",
            "highlight_target": None,
            "highlight_status": "unavailable",
        }

    original_fs_path = to_fs_path(original_image_path)
    if original_fs_path is None or not original_fs_path.exists():
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

    grounding_text = _alert_grounding_text(event, assessment)
    try:
        highlighted_path = await highlight_object(
            image_path=str(original_fs_path),
            object_name=highlight_target,
            matched_object=highlight_target,
            grounding_text=grounding_text,
            output_dir=resolve_output_dir("Storage/highlighted"),
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
            "image_path": to_stored_path(highlighted_path) or original_image_path,
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
        "alert_type": "hazard",
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
    if not is_patient_actionable_safety_assessment(
        assessment, settings.safety_alert_min_severity
    ):
        return None

    await initialize_alert_indexes()
    alert = await build_alert_document(event, assessment)
    await get_safety_alerts_collection().insert_one(alert)
    try:
        await _create_proactive_for_alert(alert)
    except Exception:
        logger.exception(
            "Proactive safety message failed for alert %s; alert remains stored",
            alert["alert_id"],
        )
    try:
        delivery_status = await deliver_patient_alert(alert)
    except Exception:
        logger.exception("Patient alert delivery failed for %s", alert["alert_id"])
        delivery_status = {"status": "failed", "error": "delivery failed"}

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


async def _create_proactive_for_alert(alert: dict[str, Any]) -> None:
    """Create a proactive turn only for actionable patient safety alerts."""

    if alert.get("target_role") != "patient":
        return
    settings = get_provider_settings()
    if not _severity_allows_alert(
        str(alert.get("severity") or "none"), settings.safety_alert_min_severity
    ):
        return
    await create_proactive_message(
        trigger_type="safety",
        text=str(alert.get("body") or alert.get("message") or "Please stay safe."),
        image_path=str(alert.get("image_path") or "") or None,
        related_id=str(alert.get("alert_id") or "") or None,
    )


def _gmail_credentials_available() -> bool:
    tools_dir = Path(__file__).resolve().parent / "Tools"
    return any(
        (tools_dir / filename).exists()
        for filename in ("credentials.json", "token.pickle")
    )


async def deliver_caretaker_alert(alert: dict[str, Any]) -> dict[str, Any]:
    """Deliver a caretaker-targeted alert through configured Gmail credentials."""

    # Provider settings loads the project .env without overriding process values.
    get_provider_settings()
    recipient = (os.getenv("FALL_ALERT_RECIPIENT_EMAIL") or "").strip()
    credentials_available = _gmail_credentials_available()
    if not recipient or not credentials_available:
        missing = []
        if not recipient:
            missing.append("recipient")
        if not credentials_available:
            missing.append("gmail_credentials")
        return {"status": "not_configured", "missing": missing}

    image_fs_path = to_fs_path(alert.get("image_path"))
    created_at = alert.get("created_at")
    timestamp = (
        created_at.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(created_at, datetime.datetime)
        else str(created_at or "")
    )

    def _send_email() -> dict[str, Any]:
        try:
            from .Tools.dementia_email import GmailAgent
        except ImportError:
            from Tools.dementia_email import GmailAgent

        agent = GmailAgent()
        return agent.send_alert_email(
            to=recipient,
            subject=alert["title"],
            alert_type=alert["title"],
            location=alert.get("room_name") or "Unknown room",
            timestamp=timestamp,
            image_path=str(image_fs_path) if image_fs_path is not None else None,
        )

    try:
        result = await asyncio.to_thread(_send_email)
    except Exception:
        logger.exception("Caretaker Gmail delivery failed for %s", alert["alert_id"])
        return {"status": "failed"}

    if result and result.get("success"):
        details: dict[str, Any] = {"status": "sent", "channel": "gmail"}
        if result.get("message_id"):
            details["message_id"] = result["message_id"]
        return details

    logger.warning("Caretaker Gmail delivery returned failure for %s", alert["alert_id"])
    return {"status": "failed", "channel": "gmail"}


async def create_alert(
    *,
    alert_type: str = "hazard",
    severity: str = "medium",
    target_role: Literal["patient", "caretaker"] = "patient",
    title: str,
    body: str,
    room_number: int,
    room_name: str = "",
    screenshot_path: str = "",
    event_id: str = "",
) -> dict[str, Any]:
    """Persist a generic alert, then dispatch it through the role's delivery channel."""

    await initialize_alert_indexes()
    now = now_local()
    alert_id = str(ObjectId())
    stored_screenshot = normalize_stored_path(screenshot_path) or ""
    alert = {
        "_id": ObjectId(alert_id),
        "alert_id": alert_id,
        "event_id": event_id,
        "alert_type": alert_type,
        "hazard_type": alert_type,
        "severity": severity,
        "confidence": 1.0,
        "target_role": target_role,
        "title": title,
        "body": body,
        "message": body,
        "detailed_explanation": "",
        "recommended_action": (
            "check_on_patient" if target_role == "caretaker" else ""
        ),
        "caretaker_recommended": target_role == "caretaker",
        "room_number": room_number,
        "room_name": room_name,
        "image_path": stored_screenshot,
        "original_image_path": stored_screenshot,
        "highlight_target": None,
        "highlight_status": (
            "fallback_original" if stored_screenshot else "unavailable"
        ),
        "status": "open",
        "delivery_status": "pending",
        "deep_link": f"memoria://alerts/{alert_id}",
        "created_at": now,
        "updated_at": now,
    }
    await get_safety_alerts_collection().insert_one(alert)

    try:
        await _create_proactive_for_alert(alert)
    except Exception:
        logger.exception(
            "Proactive safety message failed for alert %s; alert remains stored",
            alert_id,
        )

    try:
        if target_role == "caretaker":
            delivery_details = await deliver_caretaker_alert(alert)
        else:
            delivery_details = await deliver_patient_alert(alert)
    except Exception:
        logger.exception("Alert delivery failed for %s", alert_id)
        delivery_details = {"status": "failed"}

    delivery_status = delivery_details.get("status", "unknown")
    await get_safety_alerts_collection().update_one(
        {"alert_id": alert_id},
        {
            "$set": {
                "delivery_status": delivery_status,
                "delivery_details": delivery_details,
                "updated_at": now_local(),
            }
        },
    )
    alert["delivery_status"] = delivery_status
    alert["delivery_details"] = delivery_details
    return serialize_alert(alert)


def create_alert_sync(
    *,
    loop: Optional[asyncio.AbstractEventLoop],
    alert_type: str = "hazard",
    severity: str = "medium",
    target_role: Literal["patient", "caretaker"] = "patient",
    title: str,
    body: str,
    room_number: int,
    room_name: str = "",
    screenshot_path: str = "",
    event_id: str = "",
) -> Optional[concurrent.futures.Future]:
    """Submit alert creation to a running loop without blocking synchronous capture."""

    if loop is None or not loop.is_running():
        logger.error("Cannot create %s alert: capture event loop is not running", alert_type)
        return None
    future = asyncio.run_coroutine_threadsafe(
        create_alert(
            alert_type=alert_type,
            severity=severity,
            target_role=target_role,
            title=title,
            body=body,
            room_number=room_number,
            room_name=room_name,
            screenshot_path=screenshot_path,
            event_id=event_id,
        ),
        loop,
    )

    def _log_failure(completed: concurrent.futures.Future) -> None:
        try:
            completed.result()
        except Exception:
            logger.exception("Background %s alert creation failed", alert_type)

    future.add_done_callback(_log_failure)
    return future


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
        except Exception:
            logger.exception(
                "Patient alert delivery failed for device %s",
                device.get("device_id"),
            )
            results.append(
                {
                    "device_id": device.get("device_id"),
                    "status": "failed",
                    "error": "delivery failed",
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
