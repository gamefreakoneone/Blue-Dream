import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
import os
import sys
from typing import Literal, Optional

# Add the current directory to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
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
        ensure_reminder_indexes,
        ensure_memory_lifecycle_indexes,
    )
    from .jeeves import run_single_query
    from .llm.client import close_llm_clients
    from .llm.settings import get_provider_settings
    from .media_paths import to_fs_path
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
    from .timezone_utils import now_local
except ImportError:
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
        ensure_reminder_indexes,
        ensure_memory_lifecycle_indexes,
    )
    from jeeves import run_single_query
    from llm.client import close_llm_clients
    from llm.settings import get_provider_settings
    from media_paths import to_fs_path
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
    from timezone_utils import now_local

logger = logging.getLogger(__name__)
GENERIC_ERROR_DETAIL = "Something went wrong. Please try again in a moment."
_background_tasks: set[asyncio.Task] = set()

# Configure logging to show INFO level for our modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_events_indexes()
        await initialize_alert_indexes()
        await ensure_conversation_indexes()
        await ensure_profile_indexes()
        await ensure_reminder_indexes()
        await ensure_memory_lifecycle_indexes()
        await initialize_proactive_indexes()
    except Exception as exc:
        logger.warning("MongoDB index setup skipped or failed: %s", exc)

    try:
        if get_provider_settings().consolidate_on_startup:
            report = await run_consolidation()
            logger.info("Startup memory consolidation: %s", report.model_dump())
    except Exception:
        logger.exception("Startup memory consolidation failed; server will continue")

    try:
        yield
    finally:
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
        if not await mark_done(reminder_id):
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
        return {
            "messages": [
                {field: message.get(field) for field in public_fields}
                for message in messages
            ]
        }
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

# Mount the UI directory as static files (Last to act as fallback/root)
ui_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UI"
)

if os.path.exists(ui_path):
    app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui")
else:
    print(f"Warning: UI directory not found at {ui_path}")
