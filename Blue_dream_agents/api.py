from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
import os
import sys

# Add the current directory to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from jeeves import run_single_query

logger = logging.getLogger(__name__)

# Configure logging to show INFO level for our modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Jeeves API")

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


@app.post("/query")
async def query_jeeves(request: QueryRequest):
    try:
        logger.info("[API] Received query: '%s'", request.query[:100])
        response = await run_single_query(request.query)
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
        raise HTTPException(status_code=500, detail=str(e))


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
