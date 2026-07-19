"""Serve the real static UI with a deterministic spec-0007 query response."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


app = FastAPI()


@app.get("/geofence/current")
async def geofence():
    return {
        "home_lat": 37.0,
        "home_lng": -122.0,
        "radius_meters": 100,
        "source": "spec0007-ui-smoke",
    }


@app.get("/alerts/patient")
async def alerts():
    return {"alerts": []}


@app.post("/query")
async def query():
    return {
        "response_type": "activity",
        "text": (
            "I remember that you read the newspaper, made tea, and watered your "
            "bedroom plant that morning."
        ),
        "image_path": None,
        "data": {
            "recall_debug": {
                "considered_count": 4,
                "packed_count": 3,
                "excluded_count": 1,
                "memories": [
                    {
                        "id": "fact-1",
                        "type": "fact",
                        "timestamp": "2026-07-18T09:00:00-07:00",
                        "similarity": 0.0,
                        "final_score": 0.0,
                        "pinned": True,
                    },
                    {
                        "id": "event-1",
                        "type": "event",
                        "timestamp": "2026-07-18T10:00:00-07:00",
                        "similarity": 0.72,
                        "final_score": 1.04,
                        "pinned": False,
                    },
                    {
                        "id": "summary-1",
                        "type": "summary",
                        "timestamp": "2026-07-14T00:00:00-07:00",
                        "similarity": 0.66,
                        "final_score": 0.74,
                        "pinned": False,
                    },
                ],
            }
        },
    }


UI_ROOT = Path(__file__).resolve().parents[1] / "UI"
app.mount("/", StaticFiles(directory=UI_ROOT, html=True), name="ui")
