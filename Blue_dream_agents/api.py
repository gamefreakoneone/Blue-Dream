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
    from .db_client import close_mongo_client, ensure_events_indexes
    from .jeeves import run_single_query
    from .llm.ollama_runtime import close_http_client
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
    from db_client import close_mongo_client, ensure_events_indexes
    from jeeves import run_single_query
    from llm.ollama_runtime import close_http_client

logger = logging.getLogger(__name__)
GENERIC_ERROR_DETAIL = "Something went wrong. Please try again in a moment."

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
    except Exception as exc:
        logger.warning("MongoDB index setup skipped or failed: %s", exc)

    try:
        yield
    finally:
        try:
            await close_http_client()
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


@app.post("/query")
async def query_jeeves(request: QueryRequest):
    try:
        logger.info("[API] Received query: '%s'", request.query[:100])
        conversation_context = get_conversation_context(request.session_id)
        response = await run_single_query(
            request.query,
            conversation_context=conversation_context,
        )
        append_conversation_turn(
            request.session_id,
            user=request.query,
            assistant=response.text,
            response_type=response.response_type,
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
    reset_conversation(request.session_id)
    return {"ok": True}


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
capture_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Capture"
)
if os.path.exists(capture_path):
    app.mount("/capture", StaticFiles(directory=capture_path), name="capture")
else:
    print(f"Warning: Capture directory not found at {capture_path}")

# Mount the Storage directory
storage_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Storage"
)
print(f"DEBUG: Mounting storage from: {storage_path} to /storage")
if os.path.exists(storage_path):
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
