"""Serve the built spec-0013 PWA with deterministic, in-memory demo data.

Run only from the Project-Memoria conda environment:
    python -m uvicorn scripts.spec0013_ui_rehearsal:app --port 8013

This server never imports the production database layer and is safe for browser QA.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parents[1]
UI_DIST = ROOT / "UI" / "dist"
DEMO = ROOT / "Demo"
app = FastAPI()

claimed_sessions: set[str] = set()
reminders: list[dict[str, Any]] = [
    {
        "reminder_id": "rehearsal-time",
        "text": "Take my afternoon medicine",
        "trigger_type": "time",
        "due_at": "2026-07-19T15:00:00-07:00",
        "recurrence": "daily",
        "event_trigger": None,
    },
    {
        "reminder_id": "rehearsal-event",
        "text": "Take my water bottle",
        "trigger_type": "event",
        "due_at": None,
        "recurrence": "none",
        "event_trigger": {
            "room_number": 1,
            "window_start": "06:00",
            "window_end": "11:00",
            "condition": "I am leaving for a walk",
            "valid_date": "2026-07-19",
        },
    },
]


@app.post("/query")
async def query() -> dict[str, Any]:
    return {
        "response_type": "activity",
        "text": "Your white water bottle was on the bedroom table after breakfast.",
        "image_path": "/demo/whitewaterbottle%20demo.png",
        "data": {
            "recall_debug": {
                "considered_count": 5,
                "packed_count": 3,
                "excluded_count": 2,
                "memories": [
                    {
                        "id": "fact-1",
                        "type": "fact",
                        "timestamp": "2026-07-19T08:00:00-07:00",
                        "similarity": 0.0,
                        "final_score": 1.0,
                        "pinned": True,
                    },
                    {
                        "id": "event-1",
                        "type": "event",
                        "timestamp": "2026-07-19T08:35:00-07:00",
                        "similarity": 0.91,
                        "final_score": 1.18,
                        "pinned": False,
                    },
                    {
                        "id": "summary-1",
                        "type": "summary",
                        "timestamp": "2026-07-18T00:00:00-07:00",
                        "similarity": 0.78,
                        "final_score": 0.86,
                        "pinned": False,
                    },
                ],
            }
        },
    }


@app.post("/conversation/reset")
async def reset_conversation() -> dict[str, bool]:
    return {"ok": True}


@app.get("/proactive/pending")
async def pending(session_id: str = "rehearsal") -> dict[str, Any]:
    if session_id in claimed_sessions:
        return {"messages": []}
    claimed_sessions.add(session_id)
    return {
        "messages": [
            {
                "message_id": "rehearsal-safety-1",
                "trigger_type": "safety",
                "text": "The stove may still be warm. Please step back while we check it together.",
                "image_path": "/demo/whitewaterbottle%20demo.png",
                "created_at": "2026-07-19T09:00:00-07:00",
            }
        ]
    }


@app.post("/proactive/{message_id}/ack")
async def acknowledge_proactive(message_id: str) -> dict[str, bool]:
    return {"ok": bool(message_id)}


@app.get("/reminders")
async def list_reminders() -> dict[str, Any]:
    return {"reminders": reminders}


@app.post("/reminders")
async def create_reminder(payload: dict[str, Any]) -> dict[str, Any]:
    created = {"reminder_id": f"rehearsal-{len(reminders) + 1}", **payload}
    reminders.append(created)
    return created


@app.post("/reminders/{reminder_id}/done")
async def complete_reminder(reminder_id: str) -> dict[str, bool]:
    reminders[:] = [item for item in reminders if item["reminder_id"] != reminder_id]
    return {"ok": True}


@app.get("/alerts/patient")
async def list_alerts() -> dict[str, Any]:
    return {
        "alerts": [
            {
                "alert_id": "rehearsal-alert-1",
                "alert_type": "hazard",
                "severity": "medium",
                "title": "The stove may still be warm",
                "body": "Please keep a little distance while we make sure everything is settled.",
                "recommended_action": "Step away from the stove and ask a caregiver to check it.",
                "room_name": "Kitchen",
                "image_path": "/demo/whitewaterbottle%20demo.png",
                "status": "open",
                "created_at": "2026-07-19T09:00:00-07:00",
            }
        ]
    }


@app.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str) -> dict[str, bool]:
    return {"ok": bool(alert_id)}


@app.get("/geofence/current")
async def geofence_settings() -> dict[str, Any]:
    return {"home_lat": 37.0, "home_lng": -122.0, "radius_meters": 100}


@app.post("/geofence/events")
async def geofence_event() -> dict[str, Any]:
    return {"ok": True, "event_type": "exit", "distance_meters": 240}


@app.get("/memory/profile")
async def profile() -> dict[str, Any]:
    return {
        "facts": [
            {"fact_id": "fact-1", "text": "My white water bottle goes with me on morning walks.", "category": "routine", "pinned": True},
            {"fact_id": "fact-2", "text": "My daughter Maya calls after lunch.", "category": "person", "pinned": False},
        ]
    }


@app.post("/memory/profile/{fact_id}/pin")
@app.post("/memory/profile/{fact_id}/archive")
async def update_fact(fact_id: str) -> dict[str, bool]:
    return {"ok": bool(fact_id)}


@app.get("/memory/summaries")
async def summaries(days: int = 7) -> dict[str, Any]:
    return {
        "summaries": [
            {
                "summary_id": "summary-1",
                "date": "2026-07-19",
                "room_number": 1,
                "room_name": "Bedroom",
                "text": "You got ready for the day, had breakfast, and placed your water bottle on the table.",
                "source_event_count": 4,
                "created_at": dt.datetime(2026, 7, 19, 9, tzinfo=dt.timezone.utc).isoformat(),
            },
            {
                "summary_id": "summary-2",
                "date": "2026-07-18",
                "room_number": 2,
                "room_name": "Living Room",
                "text": "You read the newspaper and watered the plant by the window.",
                "source_event_count": 3,
                "created_at": dt.datetime(2026, 7, 18, 18, tzinfo=dt.timezone.utc).isoformat(),
            },
        ][:days]
    }


@app.post("/memory/consolidate")
async def consolidate() -> dict[str, int]:
    return {"groups_formed": 2, "events_consolidated": 7, "summaries_created": 2}


@app.get("/push/vapid-public-key")
async def vapid_key() -> dict[str, Any]:
    return {"enabled": False, "key": ""}


@app.post("/push/test")
async def test_push() -> dict[str, Any]:
    return {"status": "not_configured", "sent": 0, "failed": 0}


app.mount("/demo", StaticFiles(directory=DEMO), name="demo")
app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
