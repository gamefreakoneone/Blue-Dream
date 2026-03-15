# Project Memoria: Dementia Support Monitoring and Recall

Project Memoria is a dementia-support system that combines multi-room monitoring, fall detection, and memory recall assistance. The current baseline pairs a FastAPI-served patient web app with a capture pipeline that records events into MongoDB, indexes semantic memory in ChromaDB, and answers object, activity, and recall questions through a Nova-powered assistant.

![Demo GIF](Demo/shortened%20project%20meoria%20(1).gif)

## Demo Overview

Project Memoria is designed around three connected workflows:

- continuous room monitoring with fall detection and caregiver alerts
- event ingestion that stores screenshots, videos, transcripts, and canonical memory events
- a web assistant that helps find objects, recall recent activities, and answer memory-oriented questions

The UI is served directly by the FastAPI backend at `http://localhost:8000`.

## Current Capabilities

- **Fall detection with alerts**: A custom YOLO model monitors live camera feeds, applies a short stability window to reduce false positives, and can send Gmail alerts with captured screenshots.
- **Object search with current-state-first reasoning**: The assistant checks the latest room snapshots first, attempts Gemini-based localization for a highlighted image when it has a visual match, and falls back to text-only current-state or historical reasoning when needed.
- **Time and activity recall**: MongoDB-backed memory events support queries such as recent activity summaries, transcript-oriented recall, and room-based checks.
- **Semantic retrieval**: Prior events are embedded with Nova embeddings and indexed in ChromaDB so the assistant can retrieve semantically related memories.
- **Semantic-to-time grounding**: The active `/query` flow can combine semantic matches with nearby time-window context when the retrieved evidence needs additional grounding.

## Current Stack

- **Backend**: FastAPI serves the UI, `POST /query`, and static media mounts.
- **Source of truth**: MongoDB stores canonical memory events in `dementia_assistance.events`.
- **Semantic index**: ChromaDB indexes `semantic_text` embeddings under the `memory_events` collection by default.
- **Primary model runtime**: Amazon Nova on native Bedrock handles routing, answer synthesis, and embeddings.
- **Exceptions**: Gemini remains on the active path for video understanding and image localization tasks.
- **Transcription compatibility path**: OpenAI is currently used only for ingestion-time audio transcription.

Legacy note: [`Blue_dream_agents/sam3_api.py`](Blue_dream_agents/sam3_api.py) is still in the repository, but it is not part of the active object-highlighting path.

## Architecture

![Architecture Diagram](Demo/Project%20Memoria%20Architecture.png)

At a high level:

1. `Capture/camera_feed.py` records room activity, screenshots, and audio/video artifacts.
2. `Capture/video_processing_queue.py` hands completed recordings to the consolidator.
3. `Blue_dream_agents/consolidator.py` writes canonical memory events to MongoDB and attempts semantic indexing in ChromaDB.
4. `Blue_dream_agents/api.py` serves the UI and forwards `POST /query` requests into the assistant stack.
5. `Blue_dream_agents/jeeves.py` routes queries across object, time, and semantic retrieval flows.

## Prerequisites

- **Python 3.10+**
- **MongoDB** running locally unless you override `MONGODB_URI`
- **One or more webcams/cameras** for live capture
- **PyTorch/Torchvision** installed separately before `requirements.txt`
- **Credentials / keys**
  - AWS credentials or `AWS_BEARER_TOKEN_BEDROCK`
  - `GEMINI_API_KEY`
  - `OPENAI_TRANSCRIBE_API_KEY`
  - Google OAuth credentials for Gmail alerts if you want email notifications enabled

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd Project-Memoria_Dementia-Assistant
```

### 2. Install PyTorch and Torchvision

Install these in your environment before the rest of the project dependencies:

```bash
conda install pytorch torchvision -c pytorch -c nvidia
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` is the dependency source of truth for the active runtime.

### 4. Prepare MongoDB

By default the app expects:

```text
mongodb://localhost:27017
```

If your MongoDB instance lives elsewhere, set `MONGODB_URI`.

### 5. Optional Gmail alert setup

If you want fall-detection email alerts enabled:

- place `credentials.json` in `Blue_dream_agents/Tools/`
- allow the Gmail OAuth flow to generate `token.pickle`

If Gmail auth begins failing with `invalid_grant`, regenerate the local token.

## Configuration

Create a `.env` file in the repository root. The active runtime expects the following core settings:

```ini
# Required core runtime keys
GEMINI_API_KEY=your_gemini_key
OPENAI_TRANSCRIBE_API_KEY=your_openai_transcription_key

# Use either AWS credentials/profile or Bedrock API-key auth
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token

# Optional runtime overrides
MONGODB_URI=mongodb://localhost:27017
BEDROCK_AWS_REGION=us-east-1
BEDROCK_API_KEY_REGION=us-east-1
NOVA_ROUTER_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_SYNTHESIS_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_VISION_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_VISION_FALLBACK_MODEL=us.amazon.nova-lite-v1:0
NOVA_EMBEDDING_MODEL=amazon.nova-2-multimodal-embeddings-v1:0
GEMINI_SPATIAL_MODEL=gemini-2.5-flash
CHROMA_PERSIST_DIR=Storage/chroma
CHROMA_COLLECTION_NAME=memory_events
SEMANTIC_SEARCH_TOP_K=5
```

Important defaults and behavior:

- `BEDROCK_AWS_REGION` defaults to `us-east-1`
- AWS credentials are preferred when present; otherwise the runtime uses `AWS_BEARER_TOKEN_BEDROCK`
- Nova text models should use inference-profile-style IDs such as `us.amazon.nova-2-lite-v1:0`
- Nova embeddings default to `amazon.nova-2-multimodal-embeddings-v1:0`
- Chroma persistence defaults to `Storage/chroma`
- `OPENAI_API_KEY` is only a backward-compatible fallback for transcription, not the active `/query` runtime
- Gemini spatial model resolution falls back from `GEMINI_SPATIAL_MODEL` to `GEMINI_VIDEO_MODEL` to `gemini-2.5-flash`

## Running the System

### 1. Start the backend API and UI host

```bash
uvicorn Blue_dream_agents.api:app --reload
```

This serves:

- the web UI at `http://localhost:8000`
- the assistant query endpoint at `POST /query`
- static media under `/capture/*` and `/storage/*`

### 2. Start the capture pipeline

```bash
python Capture/camera_feed.py
```

This launches live camera monitoring, fall detection, and the recording pipeline. Press `q` in the camera window to stop it.

## Query / API Contract

The frontend sends assistant requests to:

```text
POST /query
```

Request body:

```json
{ "query": "Where are my keys?" }
```

Response shape:

```json
{
  "response_type": "search_result | activity | general",
  "text": "string",
  "image_path": "string | null",
  "data": "object | null"
}
```

Notes:

- `UI/script.js` renders `text` and an optional `image_path`
- object-search answers may return a highlighted image through `image_path`
- returned media paths are expected to resolve through `/capture/*` or `/storage/*`

## Repository Layout

- **`Blue_dream_agents/`**: Assistant orchestration, LLM clients/settings, semantic retrieval, time reasoning, object search, and API code
- **`Capture/`**: Camera ingestion, audio capture, video queueing, and fall detection
- **`UI/`**: Static frontend served by FastAPI
- **`Storage/`**: Runtime media, highlighted images, and the local Chroma persistence directory
- **`Demo/`**: Demo images, GIFs, and architecture visuals

## Current Limitations and Operational Notes

- `Capture/camera_feed.py` currently uses hardcoded camera indices `[1, 2]`
- the fall-alert recipient email is hardcoded in the capture path and should be treated as a local-development quirk
- Gmail alerts require local credential artifacts under `Blue_dream_agents/Tools/`
- Chroma may reset local persisted state if it detects an invalid or mismatched collection layout
- voice support code exists in the repository, but voice is not yet part of the documented primary user flow
- `requirements.txt` should be treated as the dependency source of truth over older documentation references
- room assumptions are currently fixed to `0 = Bedroom` and `1 = Living Room`

## Roadmap Snapshot

Current overhaul status is tracked in [`PLANS.md`](PLANS.md).

- **Validated current baseline**: Nova runtime integration, canonical memory events, and Gemini spatial localization are part of the active baseline.
- **Active in-progress platform work**: Semantic retrieval hardening and semantic-to-time grounding are present in the codebase and still being refined.
- **Planned next steps**: Voice support and conversation memory remain roadmap items rather than documented end-user features.

## Demo and Model Evaluation Appendix

### Object-finding examples

<p float="left">
  <img src="Demo/whitewaterbottle%20demo.png" width="45%" alt="White water bottle localization" />
  <img src="Demo/blacksmartphon%20demo.png" width="45%" alt="Smartphone localization" />
</p>

### Fall alert example

<p align="center">
  <img src="Demo/Fall%20email.jpeg" width="60%" alt="Fall detection email alert" />
</p>

### YOLO evaluation

#### Precision-Recall Curve

![PR Curve](Demo/BoxPR_curve.png)

- mAP@0.5: 0.923
- Fallen detection mAP: 0.950
- Not fallen detection mAP: 0.895

#### F1-Confidence Curve

![F1 Curve](Demo/BoxF1_curve.png)

- Best F1 score: 0.90 at confidence 0.349

#### Precision-Confidence Curve

![Precision Curve](Demo/BoxP_curve.png)

- Precision reaches 1.00 at confidence 0.949

#### Confusion Matrix

![Confusion Matrix Normalized](Demo/confusion_matrix_normalized.png)
![Confusion Matrix](Demo/confusion_matrix.png)

- Fallen detection accuracy: 94%
- Not fallen detection accuracy: 87%
