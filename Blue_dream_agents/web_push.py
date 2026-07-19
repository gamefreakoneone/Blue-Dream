"""Standards-based Web Push delivery for patient proactive messages.

This module deliberately has no FastAPI dependency. Both the API server and the
capture/ingestion process create proactive messages, so push delivery and index
initialization must work in either process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import quote

from pywebpush import WebPushException, webpush

from .db_client import (
    ensure_push_indexes as ensure_push_indexes_in_db,
    get_push_subscriptions_collection,
)
from .llm.settings import load_project_env
from .media_paths import normalize_stored_path, to_url_path
from .timezone_utils import now_local


logger = logging.getLogger(__name__)

_indexes_ready = False
_indexes_lock = asyncio.Lock()
_not_configured_logged = False


def _config() -> tuple[str, str, str]:
    load_project_env()
    private_key = (os.getenv("VAPID_PRIVATE_KEY") or "").strip()
    public_key = (os.getenv("VAPID_PUBLIC_KEY") or "").strip()
    subject = (os.getenv("VAPID_SUBJECT") or "mailto:memoria@localhost").strip()
    return private_key, public_key, subject


def _log_not_configured_once() -> None:
    global _not_configured_logged
    if _not_configured_logged:
        return
    logger.warning(
        "Web Push is disabled because VAPID_PRIVATE_KEY or VAPID_PUBLIC_KEY is missing"
    )
    _not_configured_logged = True


def get_public_key_status() -> dict[str, Any]:
    """Return the public configuration exposed by the API."""

    private_key, public_key, _ = _config()
    enabled = bool(private_key and public_key)
    if not enabled:
        _log_not_configured_once()
    return {"enabled": enabled, "key": public_key if enabled else None}


async def initialize_push_indexes() -> None:
    """Create push indexes once per process, retrying after failures."""

    global _indexes_ready
    if _indexes_ready:
        return
    async with _indexes_lock:
        if _indexes_ready:
            return
        await ensure_push_indexes_in_db()
        _indexes_ready = True


def _result(status: str, *, code: int | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"status": status, "at": now_local().isoformat()}
    if code is not None:
        value["code"] = code
    return value


async def _record_result(
    endpoint: str,
    result: dict[str, Any],
    *,
    disable: bool = False,
) -> None:
    update: dict[str, Any] = {
        "last_result": result,
        "updated_at": now_local(),
    }
    if disable:
        update["enabled"] = False
    await get_push_subscriptions_collection().update_one(
        {"endpoint": endpoint}, {"$set": update}
    )


async def _record_result_safely(
    endpoint: str,
    result: dict[str, Any],
    *,
    disable: bool = False,
) -> None:
    try:
        await _record_result(endpoint, result, disable=disable)
    except Exception:
        logger.exception("Could not store Web Push result for endpoint %s", endpoint)


async def _send_one(
    document: dict[str, Any],
    payload: dict[str, Any],
    *,
    private_key: str,
    subject: str,
) -> bool:
    endpoint = str(document.get("endpoint") or "")
    subscription_info = {
        "endpoint": endpoint,
        "keys": {
            "p256dh": str((document.get("keys") or {}).get("p256dh") or ""),
            "auth": str((document.get("keys") or {}).get("auth") or ""),
        },
    }
    try:
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=json.dumps(payload, separators=(",", ":")),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
            ttl=600,
        )
        await _record_result_safely(endpoint, _result("sent"))
        return True
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None)
        gone = code in (404, 410)
        await _record_result_safely(
            endpoint,
            _result("gone" if gone else "failed", code=code),
            disable=gone,
        )
        logger.warning("Web Push delivery failed for endpoint %s (status=%s)", endpoint, code)
        return False
    except Exception:
        await _record_result_safely(endpoint, _result("failed"))
        logger.exception("Web Push delivery failed for endpoint %s", endpoint)
        return False


async def send_to_patient_subscriptions(payload: dict[str, Any]) -> dict[str, Any]:
    """Send one JSON payload to every enabled patient browser subscription."""

    private_key, public_key, subject = _config()
    if not private_key or not public_key:
        _log_not_configured_once()
        return {"status": "not_configured", "sent": 0, "failed": 0}

    try:
        await initialize_push_indexes()
        subscriptions = [
            document
            async for document in get_push_subscriptions_collection().find(
                {"role": "patient", "enabled": True}
            )
        ]
    except Exception:
        logger.exception("Could not load Web Push subscriptions")
        return {"status": "sent", "sent": 0, "failed": 1}
    if not subscriptions:
        return {"status": "no_subscriptions", "sent": 0, "failed": 0}

    outcomes = await asyncio.gather(
        *(
            _send_one(
                document,
                payload,
                private_key=private_key,
                subject=subject,
            )
            for document in subscriptions
        )
    )
    sent = sum(outcomes)
    return {
        "status": "sent",
        "sent": sent,
        "failed": len(outcomes) - sent,
    }


async def send_for_proactive_message(document: dict[str, Any]) -> None:
    """Map a stored proactive message to its patient notification payload."""

    trigger_type = str(document.get("trigger_type") or "reminder")
    titles = {
        "safety": "Memoria noticed something",
        "reminder": "A gentle reminder",
        "morning_report": "Good morning",
    }
    message_id = str(document.get("message_id") or "")
    image_path = to_url_path(normalize_stored_path(document.get("image_path")))
    image = quote(image_path, safe="/") if image_path else None
    await send_to_patient_subscriptions(
        {
            "title": titles.get(trigger_type, "A note from Memoria"),
            "body": str(document.get("text") or ""),
            "tag": message_id,
            "url": "/#chat",
            "image": image,
            "trigger_type": trigger_type,
            "message_id": message_id,
        }
    )
