import asyncio
import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import logging
import os
import sys
from typing import Literal, Optional
from uuid import uuid4

# Add the current directory to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from . import web_push
    from .conversation_memory import (
        append_conversation_turn,
        get_conversation_context,
        reset_conversation,
    )
    from .alert_service import (
        acknowledge_alert,
        get_alert,
        get_current_geofence,
        initialize_alert_indexes,
        list_patient_alerts,
        record_geofence_event,
        register_device,
        update_current_geofence,
    )
    from .db_client import (
        close_mongo_client,
        ensure_conversation_indexes,
        ensure_events_indexes,
        ensure_profile_indexes,
        ensure_push_indexes,
        ensure_reminder_indexes,
        ensure_memory_lifecycle_indexes,
        get_memory_summaries_collection,
        get_push_subscriptions_collection,
    )
    from .jeeves import run_single_query
    from .llm.client import close_llm_clients
    from .llm.settings import get_provider_settings, load_project_env
    from .media_paths import normalize_stored_path, to_fs_path, to_url_path
    from .memory_lifecycle import pin_event, run_consolidation, unpin_event
    from .profile_memory import (
        archive_fact,
        extract_and_store,
        get_active_facts,
        pin_fact,
    )
    from .proactive_service import (
        acknowledge as acknowledge_proactive,
        check_due_reminders,
        get_pending as get_pending_proactive,
        initialize_proactive_indexes,
    )
    from .reminder_service import (
        ReminderCreate,
        create_reminder,
        list_active as list_active_reminders,
        mark_done,
    )
    from .timezone_utils import now_local, to_local
except ImportError:
    import web_push
    from conversation_memory import (
        append_conversation_turn,
        get_conversation_context,
        reset_conversation,
    )
    from alert_service import (
        acknowledge_alert,
        get_alert,
        get_current_geofence,
        initialize_alert_indexes,
        list_patient_alerts,
        record_geofence_event,
        register_device,
        update_current_geofence,
    )
    from db_client import (
        close_mongo_client,
        ensure_conversation_indexes,
        ensure_events_indexes,
        ensure_profile_indexes,
        ensure_push_indexes,
        ensure_reminder_indexes,
        ensure_memory_lifecycle_indexes,
        get_memory_summaries_collection,
        get_push_subscriptions_collection,
    )
    from jeeves import run_single_query
    from llm.client import close_llm_clients
    from llm.settings import get_provider_settings, load_project_env
    from media_paths import normalize_stored_path, to_fs_path, to_url_path
    from memory_lifecycle import pin_event, run_consolidation, unpin_event
    from profile_memory import (
        archive_fact,
        extract_and_store,
        get_active_facts,
        pin_fact,
    )
    from proactive_service import (
        acknowledge as acknowledge_proactive,
        check_due_reminders,
        get_pending as get_pending_proactive,
        initialize_proactive_indexes,
    )
    from reminder_service import (
        ReminderCreate,
        create_reminder,
        list_active as list_active_reminders,
        mark_done,
    )
    from timezone_utils import now_local, to_local

logger = logging.getLogger(__name__)
GENERIC_ERROR_DETAIL = "Something went wrong. Please try again in a moment."
_background_tasks: set[asyncio.Task] = set()


def _reminder_sweep_seconds() -> int:
    load_project_env()
    raw = (os.getenv("REMINDER_SWEEP_SECONDS") or "30").strip()
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid REMINDER_SWEEP_SECONDS=%r; using 30", raw)
        return 30
    if value < 0:
        logger.warning("REMINDER_SWEEP_SECONDS cannot be negative; using 30")
        return 30
    return value


async def _reminder_sweep_loop(seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await check_due_reminders(now_local())
        except Exception:
            logger.exception("Reminder sweep failed")

# Configure logging to show INFO level for our modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    reminder_sweep_task: Optional[asyncio.Task] = None
    try:
        await ensure_events_indexes()
        await initialize_alert_indexes()
        await ensure_conversation_indexes()
        await ensure_profile_indexes()
        await ensure_reminder_indexes()
        await ensure_memory_lifecycle_indexes()
        await initialize_proactive_indexes()
        await ensure_push_indexes()
    except Exception as exc:
        logger.warning("MongoDB index setup skipped or failed: %s", exc)

    try:
        if get_provider_settings().consolidate_on_startup:
            report = await run_consolidation()
            logger.info("Startup memory consolidation: %s", report.model_dump())
    except Exception:
        logger.exception("Startup memory consolidation failed; server will continue")

    sweep_seconds = _reminder_sweep_seconds()
    if sweep_seconds:
        reminder_sweep_task = asyncio.create_task(
            _reminder_sweep_loop(sweep_seconds), name="reminder-sweep"
        )
        logger.info("Reminder sweep enabled every %s seconds", sweep_seconds)
    else:
        logger.info("Reminder sweep disabled by REMINDER_SWEEP_SECONDS=0")

    try:
        yield
    finally:
        if reminder_sweep_task is not None:
            reminder_sweep_task.cancel()
            await asyncio.gather(reminder_sweep_task, return_exceptions=True)
        if _background_tasks:
            await asyncio.gather(*list(_background_tasks), return_exceptions=True)
        try:
            await close_llm_clients()
        finally:
            await close_mongo_client()


app = FastAPI(title="Jeeves API", lifespan=lifespan)

# Allow CORS for development convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class ConversationResetRequest(BaseModel):
    session_id: str


class DeviceRegistrationRequest(BaseModel):
    device_id: str
    platform: Literal["android", "ios", "web"] = "android"
    push_provider: Literal["fcm", "expo", "none"] = "fcm"
    push_token: str
    role: Literal["patient", "caretaker"] = "patient"


class AlertAckRequest(BaseModel):
    action: Literal["ok", "returning", "dismissed"]


class GeofenceSettingsRequest(BaseModel):
    home_lat: float
    home_lng: float
    radius_meters: float


class GeofenceEventRequest(BaseModel):
    event_type: Literal["exit", "enter"]
    latitude: float
    longitude: float
    device_id: Optional[str] = None


class WebPushKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class WebPushSubscription(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: WebPushKeys


class PushSubscribeRequest(BaseModel):
    subscription: WebPushSubscription
    role: Literal["patient"] = "patient"


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1)


async def _extract_turn_memory_safely(
    user_text: str,
    assistant_text: str,
    session_id: Optional[str],
) -> None:
    try:
        await extract_and_store(
            user_text,
            assistant_text,
            session_id=session_id,
        )
    except Exception:
        logger.exception("Post-response durable-memory extraction failed")


def _schedule_turn_memory_extraction(
    user_text: str,
    assistant_text: str,
    session_id: Optional[str],
) -> None:
    task = asyncio.create_task(
        _extract_turn_memory_safely(user_text, assistant_text, session_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.post("/query")
async def query_jeeves(request: QueryRequest):
    try:
        logger.info("[API] Received query: '%s'", request.query[:100])
        conversation_context = await get_conversation_context(request.session_id)
        response = await run_single_query(
            request.query,
            conversation_context=conversation_context,
        )
        await append_conversation_turn(request.session_id, "user", request.query)
        await append_conversation_turn(request.session_id, "assistant", response.text)
        _schedule_turn_memory_extraction(
            request.query,
            response.text,
            request.session_id,
        )
        logger.info(
            "[API] Response: type=%s, has_image=%s, text_length=%d",
            response.response_type,
            bool(response.image_path),
            len(response.text),
        )
        if response.image_path:
            logger.info("[API] Image path in response: %s", response.image_path)
        return response.model_dump()
    except Exception as e:
        logger.exception("[API] Query failed: '%s'", request.query[:100])
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/conversation/reset")
async def reset_conversation_session(request: ConversationResetRequest):
    await reset_conversation(request.session_id)
    return {"ok": True}


@app.get("/memory/profile")
async def get_memory_profile():
    try:
        return {"facts": await get_active_facts()}
    except Exception:
        logger.exception("Profile memory list failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/memory/profile/{fact_id}/pin")
async def pin_memory_profile_fact(fact_id: str):
    try:
        if not await pin_fact(fact_id):
            raise HTTPException(status_code=404, detail="Profile fact not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Profile fact pin failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/memory/profile/{fact_id}/archive")
async def archive_memory_profile_fact(fact_id: str):
    try:
        if not await archive_fact(fact_id):
            raise HTTPException(status_code=404, detail="Profile fact not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Profile fact archive failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/memory/consolidate")
async def consolidate_memory_events():
    try:
        return (await run_consolidation()).model_dump(mode="json")
    except Exception:
        logger.exception("Memory consolidation endpoint failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


def _summary_value(value):
    if isinstance(value, dt.datetime):
        return to_local(value).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


@app.get("/memory/summaries")
async def get_memory_summaries(days: int = Query(default=7, ge=1, le=365)):
    try:
        cutoff = now_local().date() - dt.timedelta(days=days - 1)
        cursor = get_memory_summaries_collection().find(
            {"date": {"$gte": cutoff.isoformat()}}
        ).sort([("date", -1), ("room_number", 1)])
        summaries = []
        async for document in cursor:
            source_event_ids = document.get("source_event_ids") or []
            summaries.append(
                {
                    "summary_id": str(document.get("summary_id") or ""),
                    "date": _summary_value(document.get("date")),
                    "room_number": document.get("room_number"),
                    "room_name": str(document.get("room_name") or ""),
                    "text": str(document.get("text") or ""),
                    "source_event_count": len(source_event_ids),
                    "created_at": _summary_value(document.get("created_at")),
                }
            )
        return {"summaries": summaries}
    except Exception:
        logger.exception("Memory summary list failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/memory/events/{event_id}/pin")
async def pin_memory_event(event_id: str):
    try:
        if not await pin_event(event_id):
            raise HTTPException(status_code=404, detail="Memory event not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Memory event pin failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/memory/events/{event_id}/unpin")
async def unpin_memory_event(event_id: str):
    try:
        if not await unpin_event(event_id):
            raise HTTPException(status_code=404, detail="Memory event not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Memory event unpin failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/reminders")
async def get_reminders():
    try:
        return {"reminders": await list_active_reminders()}
    except Exception:
        logger.exception("Reminder list failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/reminders")
async def post_reminder(request: ReminderCreate):
    try:
        return await create_reminder(request, source="api", origin_context=None)
    except Exception:
        logger.exception("Reminder creation failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/reminders/{reminder_id}/done")
async def complete_reminder(reminder_id: str):
    try:
        if not await mark_done(reminder_id, mode="patient"):
            raise HTTPException(status_code=404, detail="Reminder not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Reminder completion failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/proactive/pending")
async def get_proactive_messages(session_id: Optional[str] = None):
    try:
        now = now_local()
        try:
            await check_due_reminders(now)
        except Exception:
            logger.exception(
                "Poll-driven reminder check failed; returning existing proactive messages"
            )
        messages = await get_pending_proactive(now)
        if session_id:
            for message in messages:
                try:
                    await append_conversation_turn(
                        session_id, "assistant", str(message.get("text") or "")
                    )
                except Exception:
                    logger.exception(
                        "Could not append proactive message %s to session %s",
                        message.get("message_id"),
                        session_id,
                    )
        public_fields = (
            "message_id",
            "trigger_type",
            "text",
            "image_path",
            "action",
            "created_at",
        )
        public_messages = []
        for message in messages:
            public_message = {
                field: message.get(field) for field in public_fields
            }
            public_message["image_path"] = to_url_path(
                normalize_stored_path(message.get("image_path"))
            )
            public_messages.append(public_message)
        return {"messages": public_messages}
    except Exception:
        logger.exception("Proactive pending-message poll failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/proactive/{message_id}/ack")
async def acknowledge_proactive_message(message_id: str):
    try:
        if not await acknowledge_proactive(message_id):
            raise HTTPException(status_code=404, detail="Proactive message not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Proactive message acknowledgement failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/push/vapid-public-key")
async def get_vapid_public_key():
    return web_push.get_public_key_status()


@app.post("/push/subscribe")
async def subscribe_to_push(request: PushSubscribeRequest, http_request: Request):
    try:
        await web_push.initialize_push_indexes()
        now = now_local()
        endpoint = request.subscription.endpoint.strip()
        if not endpoint:
            raise HTTPException(status_code=400, detail="endpoint is required")
        subscription_id = f"ps_{uuid4().hex[:12]}"
        collection = get_push_subscriptions_collection()
        await collection.update_one(
            {"endpoint": endpoint},
            {
                "$set": {
                    "keys": request.subscription.keys.model_dump(),
                    "role": request.role,
                    "user_agent": http_request.headers.get("user-agent", ""),
                    "enabled": True,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "subscription_id": subscription_id,
                    "endpoint": endpoint,
                    "created_at": now,
                    "last_result": None,
                },
            },
            upsert=True,
        )
        stored = await collection.find_one({"endpoint": endpoint})
        return {
            "ok": True,
            "subscription_id": str((stored or {}).get("subscription_id") or subscription_id),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Push subscription registration failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/push/unsubscribe")
async def unsubscribe_from_push(request: PushUnsubscribeRequest):
    try:
        await web_push.initialize_push_indexes()
        endpoint = request.endpoint.strip()
        if not endpoint:
            raise HTTPException(status_code=400, detail="endpoint is required")
        await get_push_subscriptions_collection().update_one(
            {"endpoint": endpoint},
            {"$set": {"enabled": False, "updated_at": now_local()}},
        )
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Push subscription removal failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/push/test")
async def send_test_push():
    try:
        test_id = f"test_{uuid4().hex[:12]}"
        result = await web_push.send_to_patient_subscriptions(
            {
                "title": "Memoria notifications are ready",
                "body": "Gentle reminders are turned on.",
                "tag": test_id,
                "url": "/#chat",
                "image": None,
                "trigger_type": "test",
                "message_id": test_id,
            }
        )
        return {"status": result["status"], "sent": int(result.get("sent", 0))}
    except Exception:
        logger.exception("Test push failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/devices/register")
async def register_patient_device(request: DeviceRegistrationRequest):
    if not request.device_id.strip():
        raise HTTPException(status_code=400, detail="device_id is required")
    if request.push_provider != "none" and not request.push_token.strip():
        raise HTTPException(status_code=400, detail="push_token is required")
    try:
        return await register_device(
            device_id=request.device_id.strip(),
            platform=request.platform,
            push_provider=request.push_provider,
            push_token=request.push_token.strip(),
            role=request.role,
        )
    except Exception as exc:
        logger.exception("Device registration failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/alerts/patient")
async def get_patient_alerts(status: str = "open"):
    try:
        return {"alerts": await list_patient_alerts(status=status)}
    except Exception as exc:
        logger.exception("Patient alert list failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/alerts/{alert_id}")
async def get_alert_detail(alert_id: str):
    try:
        alert = await get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Alert detail failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, request: AlertAckRequest):
    try:
        alert = await acknowledge_alert(alert_id, request.action)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Alert acknowledgement failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.get("/geofence/current")
async def get_geofence_settings():
    try:
        return await get_current_geofence()
    except Exception as exc:
        logger.exception("Geofence read failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.put("/geofence/current")
async def set_geofence_settings(request: GeofenceSettingsRequest):
    if request.radius_meters <= 0:
        raise HTTPException(status_code=400, detail="radius_meters must be positive")
    try:
        return await update_current_geofence(
            home_lat=request.home_lat,
            home_lng=request.home_lng,
            radius_meters=request.radius_meters,
        )
    except Exception as exc:
        logger.exception("Geofence update failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


@app.post("/geofence/events")
async def create_geofence_event(request: GeofenceEventRequest):
    try:
        return await record_geofence_event(
            event_type=request.event_type,
            latitude=request.latitude,
            longitude=request.longitude,
            device_id=request.device_id,
        )
    except Exception as exc:
        logger.exception("Geofence event failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR_DETAIL)


# Mount the Capture directory to serve images
capture_path = to_fs_path("Capture")
if capture_path is not None and capture_path.exists():
    app.mount("/capture", StaticFiles(directory=capture_path), name="capture")
else:
    print(f"Warning: Capture directory not found at {capture_path}")

# Mount the Storage directory
storage_path = to_fs_path("Storage")
print(f"DEBUG: Mounting storage from: {storage_path} to /storage")
if storage_path is not None and storage_path.exists():
    app.mount("/storage", StaticFiles(directory=storage_path), name="storage")
else:
    print(f"Warning: Storage directory not found at {storage_path}")

# Mount the built UI as static files (last to act as fallback/root).
ui_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UI", "dist"
)

if os.path.exists(ui_path):
    app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui")
else:
    logger.warning(
        "UI build not found at %s; the API will run without the web UI. "
        "Run: cd UI && npm run build",
        ui_path,
    )
