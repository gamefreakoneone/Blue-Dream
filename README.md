# Project Memoria: Gemma-Powered Memory and Safety Support for Dementia Care

Project Memoria is a dementia-support prototype built for the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon/overview). It combines home monitoring, grounded memory recall, object finding, safety reasoning, and patient-facing mobile guidance.

At its core, Memoria uses **Gemma 4 E2B through local Ollama** as the reasoning layer for routing, recall synthesis, semantic evidence judging, current-image object checks, safety decisions, and patient-facing explanations. MongoDB stores durable memory events, ChromaDB indexes semantic memory using **Ollama embeddings** from `nomic-embed-text`, and the web and mobile apps turn those memories into practical support for patients and caregivers. This makes Memoria a natural fit for the hackathon's Ollama Local Ops special tech track as well as the health and safety impact themes.

![Demo GIF](Demo/shortened%20project%20meoria%20(1).gif)

## Why It Matters

People living with dementia can lose confidence in ordinary moments: "Where are my keys?", "What room was I in?", "Was I cooking earlier?", or "How do I get home?" Caregivers face the opposite problem: they need enough context to help, but they cannot watch every room event or manually interpret every recording.

Memoria is designed around one practical idea: use local, grounded AI to help patients recover context and help caregivers trust the evidence behind safety alerts.

## What Memoria Does

- **Grounded memory chat**: Patients can ask natural-language questions about objects, activities, rooms, and recent events.
- **Current-state object finding**: The assistant checks the latest room snapshots first, then falls back to historical memory when the object is not currently visible.
- **Semantic recall**: Past room events are normalized into canonical memory records, embedded locally with Ollama, and indexed in ChromaDB for evidence retrieval.
- **Safety reasoning prototype**: Factual observations from room events can be judged by Gemma for patient-actionable risks, such as unattended cooking or ambiguous hazards.
- **Patient web UI**: FastAPI serves a lightweight Memoria chat interface at `http://localhost:8000`.
- **Expo mobile app**: The React Native app supports chat, New Chat, alert list/detail screens, acknowledgement actions, geofence guidance, deep links, and notification scaffolding.
- **Fall detection**: A custom YOLO model watches live camera feeds and can notify a caregiver or emergency contact through the alert path.

## Gemma 4 Usage

Gemma is not used as a generic chatbot wrapper. It owns the main reasoning decisions in the prototype:

- **Query routing**: decides whether a patient question needs object search, time/activity recall, semantic memory retrieval, or a general response.
- **Grounded answer synthesis**: turns retrieved memory evidence into concise patient-facing responses.
- **Semantic evidence judging**: checks whether retrieved memories actually support the answer before responding.
- **Current-image object checks**: inspects latest room snapshots through Ollama multimodal input to decide whether an object is visible now before sending matched images to Gemini for highlighting.
- **Safety warning decisions**: judges factual scene observations and decides whether an alert is warranted, how severe it is, and how to explain it safely.

Ollama is also the local embedding runtime for memory search. Memoria uses `nomic-embed-text` vectors in ChromaDB, so semantic recall does not depend on Amazon/Nova embeddings in the primary hackathon path.

Gemini remains on the active path for reliable full-video perception and precise spatial localization/highlighting. Audio transcription is a current prototype dependency used during ingestion. Bedrock/Nova code remains in the repository as optional legacy/future paths, not the primary hackathon runtime.

## Demo Flow

1. A room camera records a short event when activity is detected.
2. The backend extracts video/audio evidence and stores a canonical memory event in MongoDB.
3. The event's `semantic_text` is embedded locally with Ollama `nomic-embed-text` and indexed in ChromaDB.
4. A patient asks, "Where are my keys?" or "What was I doing today?"
5. Gemma routes the query, judges evidence quality, and synthesizes a grounded response.
6. If Gemma sees the object in a current-room image, Memoria sends that matched image to Gemini Spatial for bounding-box highlighting.
7. If a safety event is detected, Gemma judges whether the patient or caregiver should be alerted.
8. The mobile app can show the alert detail, acknowledgement actions, and geofence guidance.

## Architecture

![Project Memoria Gemma Architecture](Demo/Project%20Memoria%20Gemma%20Architecture%20v2.png)

At a high level:

1. `Capture/camera_feed.py` records room activity, screenshots, audio, and video artifacts.
2. `Capture/video_processing_queue.py` hands completed recordings to the consolidator.
3. `Blue_dream_agents/consolidator.py` normalizes evidence and writes memory events to MongoDB.
4. `Blue_dream_agents/semantic_search.py` and `Blue_dream_agents/vector_store.py` maintain the ChromaDB semantic index.
5. `Blue_dream_agents/api.py` serves the web UI, mobile-compatible APIs, and static media.
6. `Blue_dream_agents/jeeves.py` routes patient queries through object, time, semantic, and general response flows.
7. `Blue_dream_agents/safety_agent.py` and `Blue_dream_agents/alert_service.py` support safety decisions and alert records.

## Current Stack

- **Local reasoning**: Gemma 4 E2B via Ollama (`gemma4:e2b`)
- **Local embeddings**: Ollama `nomic-embed-text` for ChromaDB semantic memory
- **Backend**: FastAPI
- **Durable event store**: MongoDB `dementia_assistance.events`
- **Alert store**: MongoDB `dementia_assistance.safety_alerts`
- **Semantic index**: ChromaDB collection `memory_events`
- **Video perception**: Gemini video models
- **Spatial highlighting**: Gemini spatial localization
- **Audio transcription**: current prototype transcription dependency
- **Patient web app**: Static HTML/CSS/JS served by FastAPI
- **Patient mobile app**: Expo React Native with Expo Router
- **Computer vision**: OpenCV + Ultralytics YOLO

## Prerequisites

- Windows + PowerShell is the primary development environment used by this project.
- Python 3.10+
- MongoDB running locally unless `MONGODB_URI` overrides it
- Ollama running locally with:
  - `gemma4:e2b`
  - `nomic-embed-text`
- One or more webcams/cameras for live capture
- PyTorch/Torchvision installed separately before `requirements.txt`
- Node.js and npm for the mobile app
- Required keys:
  - `GEMINI_API_KEY`
  - `OPENAI_TRANSCRIBE_API_KEY`
- Optional keys/config:
  - Firebase service account settings for remote push delivery
  - Gmail OAuth credentials for caregiver email alerts
  - Bedrock/Nova credentials only for optional legacy paths

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd Blue-Dream
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

### 4. Prepare Ollama models

```bash
ollama pull gemma4:e2b
ollama pull nomic-embed-text
```

Confirm both models are available:

```bash
ollama list
```

### 5. Prepare MongoDB

By default the app expects:

```text
mongodb://localhost:27017
```

If your MongoDB instance lives elsewhere, set `MONGODB_URI`.

### 6. Optional Gmail alert setup

If you want caregiver email alerts enabled:

- place `credentials.json` in `Blue_dream_agents/Tools/`
- allow the Gmail OAuth flow to generate `token.pickle`

Never commit credentials, tokens, service-account files, or local auth artifacts.

## Configuration

Create a `.env` file in the repository root. The current hackathon runtime uses Gemma/Ollama by default:

```ini
# Required core runtime keys
GEMINI_API_KEY=your_gemini_key
OPENAI_TRANSCRIBE_API_KEY=your_openai_transcription_key

# Local Gemma/Ollama reasoning
LOCAL_LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
GEMMA_TEXT_MODEL=gemma4:e2b
GEMMA_VISION_MODEL=gemma4:e2b

# Local semantic retrieval
EMBEDDING_PROVIDER=ollama
LOCAL_EMBEDDING_MODEL=nomic-embed-text
CHROMA_EMBEDDING_DIMENSION=768
CHROMA_PERSIST_DIR=Storage/chroma
CHROMA_COLLECTION_NAME=memory_events
SEMANTIC_SEARCH_TOP_K=5

# Database
MONGODB_URI=mongodb://localhost:27017

# Gemini perception support
GEMINI_VIDEO_MODEL=gemini-3-flash-preview
GEMINI_VIDEO_FALLBACK_MODELS=gemini-2.5-flash
GEMINI_VIDEO_MAX_RETRIES=3
GEMINI_VIDEO_RETRY_BASE_SECONDS=4
GEMINI_SPATIAL_MODEL=gemini-2.5-flash

# Safety and alert prototype
SAFETY_AGENT_ENABLED=true
SAFETY_ALERT_MIN_SEVERITY=medium

# Optional Firebase push configuration
FIREBASE_PROJECT_ID=<firebase-project-id>
FIREBASE_CREDENTIALS_PATH=<gitignored-service-account-json-path>
FIREBASE_ANDROID_PACKAGE=<android-package-name>

# Optional geofence configuration
PATIENT_HOME_LAT=<latitude>
PATIENT_HOME_LNG=<longitude>
PATIENT_GEOFENCE_RADIUS_METERS=<radius>
```

Mobile development uses `Mobile/.env`:

```ini
EXPO_PUBLIC_API_BASE_URL=http://<your-lan-ip>:8000
```

Metro reads this at startup, so restart `npx expo start` after changing it.

Optional legacy Bedrock/Nova settings still exist for older paths such as Bedrock embeddings and voice experiments. They are not required for the primary Gemma recall, routing, synthesis, current-image object check, or safety decision flow.

## Running the System

### 1. Start the backend API and web UI

```powershell
uvicorn Blue_dream_agents.api:app --reload
```

This serves:

- web UI at `http://localhost:8000`
- assistant query endpoint at `POST /query`
- static media under `/capture/*` and `/storage/*`

### 2. Start the backend for LAN/mobile access

```powershell
uvicorn Blue_dream_agents.api:app --reload --host 0.0.0.0
```

Use this when the Expo mobile app needs to reach the backend from a phone or emulator on the same network.

### 3. Start the capture pipeline

```powershell
python Capture/camera_feed.py
```

This launches live camera monitoring, fall detection, and the recording pipeline. Press `q` in the camera window to stop it.

### 4. Start the mobile app

```powershell
cd Mobile && npx expo start
```

Expo Go can test chat, local notification behavior, alert screens, deep links, and geofence navigation. Real backend-triggered remote push on Android requires an EAS development build with Firebase/FCM configuration.

## API Contracts

### Query

```text
POST /query
```

Request body:

```json
{ "query": "Where are my keys?" }
```

Optional session-aware request:

```json
{ "query": "What room was that in?", "session_id": "browser-session-id" }
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

### Conversation Reset

```text
POST /conversation/reset
```

Request body:

```json
{ "session_id": "browser-session-id" }
```

Response body:

```json
{ "ok": true }
```

Conversation memory is process-local and short-term only. It is not durable patient memory and is not embedded in ChromaDB.

### Mobile Alerts

```text
POST /devices/register
GET /alerts/patient?status=open
GET /alerts/{alert_id}
POST /alerts/{alert_id}/ack
```

Acknowledgement request body:

```json
{ "action": "ok | returning | dismissed" }
```

Alert detail responses are JSON-safe and include fields such as `alert_id`, `event_id`, `hazard_type`, `severity`, `title`, `body`, `detailed_explanation`, `recommended_action`, `room_name`, `image_path`, `status`, and `deep_link`.

### Geofence

```text
GET /geofence/current
PUT /geofence/current
POST /geofence/events
```

Geofence update body:

```json
{ "home_lat": 0.0, "home_lng": 0.0, "radius_meters": 100 }
```

Geofence event body:

```json
{ "event_type": "exit | enter", "latitude": 0.0, "longitude": 0.0, "device_id": "phone-id" }
```

The first geofence implementation is intentionally prototype-simple: the backend stores one default boundary, the mobile app checks location locally, and the app launches Google Maps navigation when the patient taps "Guide me home."

## Repository Layout

- **`Blue_dream_agents/`**: FastAPI backend, Gemma/Ollama runtime, assistant orchestration, memory retrieval, safety agent, alert service, and LLM settings
- **`Capture/`**: Camera ingestion, audio capture, video queueing, and fall detection
- **`UI/`**: Static patient web UI served by FastAPI
- **`Mobile/`**: Expo React Native patient app
- **`Storage/`**: Runtime media, highlighted images, and local Chroma persistence
- **`Demo/`**: Demo images, GIFs, architecture visuals, and evaluation assets
- **`benchmarks/`**: Reference benchmarking utilities and architecture notes

## Prototype Boundaries and Operational Notes

- Memoria is a functional prototype, not a medical device or emergency-response replacement.
- Gemma/Ollama is the active local reasoning runtime, but the current implementation still uses Gemini for full-video perception and spatial localization.
- Audio transcription is currently handled through a prototype dependency during ingestion.
- Remote Firebase push delivery is scaffolded but still requires final Firebase/device validation for production-style Android push.
- Expo Go on Android SDK 54 does not support remote push notifications; use an EAS development build for real FCM testing.
- `Capture/camera_feed.py` currently uses hardcoded camera indices `[1, 2]`.
- Room assumptions are currently fixed to `0 = Bedroom` and `1 = Living Room`.
- Gmail alerts require local credential artifacts under `Blue_dream_agents/Tools/`.
- Chroma may reset local persisted state if it detects an invalid or mismatched collection layout.
- `Storage/` contains runtime media and should be treated as generated data, not source code.

## Roadmap Snapshot

Current overhaul status is tracked in [`PLANS.md`](PLANS.md).

- **Validated**: Gemma/Ollama text runtime, local semantic retrieval, conversation session memory, memory stack hardening, canonical MongoDB events, and ChromaDB indexing.
- **In progress**: Gemma safety agent, alert delivery, and final mobile validation.
- **Planned**: caretaker dashboard, demo/submission package polish, and local Gemma frame-sampling vision experiments.

## Kaggle Project Description

**Project Memoria is a Gemma-powered dementia support system that helps patients answer memory questions and helps caregivers respond to safety risks at home.**

People living with dementia often lose confidence in ordinary moments: "Where are my keys?", "Was I in the kitchen today?", "Did I leave something dangerous behind?" Caregivers face the opposite problem: they need enough context to help, but they cannot watch continuously or interpret every home event manually. Memoria turns room monitoring into grounded, patient-facing memory assistance and actionable safety alerts.

The system records multi-room home events, stores them as canonical memory records in MongoDB, indexes semantic memory in ChromaDB, and exposes the experience through a web chat and Expo React Native patient app. A patient can ask natural questions about objects, activities, or recent context. Memoria first checks the latest room snapshots for current object presence, then falls back to historical event memory when needed. Answers are grounded in stored evidence rather than free-form chatbot guessing, and image paths can point back to captured or highlighted evidence.

Gemma 4 E2B is the core reasoning layer. Running locally through Ollama, Gemma handles query routing, memory answer synthesis, semantic evidence judging, current-image object-presence checks, and safety-warning decisions. Ollama also powers the local embedding path with `nomic-embed-text`, which lets Memoria build semantic memory search without relying on Amazon/Nova embeddings. This matters for dementia care because privacy, trust, and low-latency local reasoning are not nice-to-have qualities; they are part of whether the system can be responsibly used in a home. Gemma decides whether evidence is strong enough to answer, whether a safety concern deserves a patient-facing warning, and how to explain that warning clearly.

Memoria uses other models only where they are the right tool for perception. Gemini supports full-video understanding and spatial image localization, while audio transcription remains a current ingestion-time prototype dependency. MongoDB remains the source of truth, and ChromaDB is a rebuildable semantic index. This separation keeps the architecture honest: Gemma is the local reasoning and decision layer, while perception tools extract observations from media.

The mobile app extends the system beyond a desktop demo. It supports chat with short-term session memory, alert list/detail screens, acknowledgement actions, geofence guidance, deep links, and push-notification scaffolding. For the hackathon prototype, alert records and mobile flows are implemented, while full remote FCM delivery requires final Firebase/device validation.

The goal of Memoria is not to replace caregivers. It is to give patients more independence in small moments and give caregivers more trustworthy context when intervention is needed. The demo shows an end-to-end path from home monitoring, to memory event creation, to Gemma-grounded recall or safety reasoning, to a patient-facing response.

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

Legacy note: [`Blue_dream_agents/sam3_api.py`](Blue_dream_agents/sam3_api.py) is still in the repository, but it is not part of the active object-highlighting path.
