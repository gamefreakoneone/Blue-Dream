# Project Memoria: Memory and Safety Support for Dementia Care

Project Memoria is a memory-grounded, voice-enabled dementia-support prototype. It combines home monitoring, grounded recall, object finding, safety reasoning, and patient-facing guidance for two 2026 hackathon submissions: Qwen Cloud MemoryAgent and OpenAI Build Week.

One async provider layer serves reasoning, structured output, vision, embeddings, and transcription through OpenAI-compatible APIs. `LLM_PROVIDER=qwen|openai|ollama` selects the profile, with Qwen Cloud as the rebuild default. MongoDB remains the durable source of truth; ChromaDB holds rebuildable, provider-specific semantic indexes.

![Demo GIF](Demo/shortened%20project%20meoria%20(1).gif)

## Why It Matters

People living with dementia can lose confidence in ordinary moments: "Where are my keys?", "What room was I in?", "Was I cooking earlier?", or "How do I get home?" Caregivers face the opposite problem: they need enough context to help, but they cannot watch every room event or manually interpret every recording.

Memoria is designed around one practical idea: use local, grounded AI to help patients recover context and help caregivers trust the evidence behind safety alerts.

## What Memoria Does

- **Grounded memory chat**: Patients can ask natural-language questions about objects, activities, rooms, and recent events.
- **Current-state object finding**: The assistant checks the latest room snapshots first, then falls back to historical memory when the object is not currently visible.
- **Semantic recall**: Past room events are normalized into canonical memory records, embedded through the configured provider, and indexed in ChromaDB for evidence retrieval.
- **Safety reasoning prototype**: Factual observations from room events can be judged for patient-actionable risks, such as unattended cooking or ambiguous hazards.
- **Patient web UI**: FastAPI serves a lightweight Memoria chat interface at `http://localhost:8000`.
- **Expo mobile app**: The React Native app supports chat, New Chat, alert list/detail screens, acknowledgement actions, geofence guidance, deep links, and notification scaffolding.
- **Fall detection**: A custom YOLO model watches live camera feeds and can notify a caregiver or emergency contact through the alert path.

## Provider Architecture

The configured provider owns the main reasoning decisions in the prototype:

- **Query routing**: decides whether a patient question needs object search, time/activity recall, semantic memory retrieval, or a general response.
- **Grounded answer synthesis**: turns retrieved memory evidence into concise patient-facing responses.
- **Semantic evidence judging**: checks whether retrieved memories actually support the answer before responding.
- **Current-image object checks**: inspects current room snapshots before sending matched images to the configured spatial provider for highlighting.
- **Safety warning decisions**: judges factual scene observations and decides whether an alert is warranted, how severe it is, and how to explain it safely.

The same client exposes text, structured, multimodal, video, embeddings, ASR, and TTS capability boundaries. Qwen ASR/video and TTS are intentionally completed by specs 0005 and 0009; spec 0003 provides offline-tested OpenAI transcription fallback plumbing and explicit pending stubs.

Gemini remains available for video perception and spatial localization. Ollama is an optional OpenAI-compatible local profile and is not a prerequisite. Legacy Strands and Bedrock SDK paths have been removed.

## Demo Flow

1. A room camera records a short event when activity is detected.
2. The backend extracts video/audio evidence and stores a canonical memory event in MongoDB.
3. The event's `semantic_text` is embedded through the configured provider and indexed in its own Chroma collection.
4. A patient asks, "Where are my keys?" or "What was I doing today?"
5. The configured model routes the query, judges evidence quality, and synthesizes a grounded response.
6. If the object is present in a current-room image, Memoria sends that image to the configured spatial provider for highlighting.
7. If a safety event is detected, the configured model judges whether the patient or caregiver should be alerted.
8. The mobile app can show the alert detail, acknowledgement actions, and geofence guidance.

## Architecture

![Project Memoria Architecture](Demo/Project%20Memoria%20Gemma%20Architecture%20v2.png)

At a high level:

1. `Capture/camera_feed.py` records room activity, screenshots, audio, and video artifacts.
2. `Capture/video_processing_queue.py` hands completed recordings to the consolidator.
3. `Blue_dream_agents/consolidator.py` normalizes evidence and writes memory events to MongoDB.
4. `Blue_dream_agents/semantic_search.py` and `Blue_dream_agents/vector_store.py` maintain the ChromaDB semantic index.
5. `Blue_dream_agents/api.py` serves the web UI, mobile-compatible APIs, and static media.
6. `Blue_dream_agents/jeeves.py` routes patient queries through object, time, semantic, and general response flows.
7. `Blue_dream_agents/safety_agent.py` and `Blue_dream_agents/alert_service.py` support safety decisions and alert records.

## Current Stack

- **Reasoning and embeddings**: Qwen Cloud by default through the unified async provider client
- **Backend**: FastAPI
- **Durable event store**: MongoDB `dementia_assistance.events`
- **Alert store**: MongoDB `dementia_assistance.safety_alerts`
- **Semantic index**: ChromaDB collections named `memory_events__{provider}__{model_slug}__{dim}`
- **Video perception**: Gemini video models
- **Spatial highlighting**: Gemini spatial localization
- **Audio transcription**: offline-tested OpenAI fallback; Qwen live path lands in spec 0005
- **Patient web app**: Static HTML/CSS/JS served by FastAPI
- **Patient mobile app**: Expo React Native with Expo Router
- **Computer vision**: OpenCV + Ultralytics YOLO

## Prerequisites

- Windows + PowerShell is the primary development environment used by this project.
- Python 3.10+
- MongoDB running locally unless `MONGODB_URI` overrides it
- One or more webcams/cameras for live capture
- PyTorch/Torchvision installed separately before `requirements.txt`
- Node.js and npm for the mobile app
- Required keys depend on the selected providers. The default Qwen profile uses `DASHSCOPE_API_KEY` (or `QWEN_APIKEY` fallback); Gemini features use `GEMINI_API_KEY`.
- Optional keys/config:
  - Firebase service account settings for remote push delivery
  - Gmail OAuth credentials for caregiver email alerts
  - `OPENAI_API_KEY` for the offline-tested OpenAI profile or transcription fallback

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

### 4. Prepare MongoDB

By default the app expects:

```text
mongodb://localhost:27017
```

If your MongoDB instance lives elsewhere, set `MONGODB_URI`.

### 5. Optional Gmail alert setup

If you want caregiver email alerts enabled:

- place `credentials.json` in `Blue_dream_agents/Tools/`
- allow the Gmail OAuth flow to generate `token.pickle`

Never commit credentials, tokens, service-account files, or local auth artifacts.

## Configuration

Copy `.env.example` to `.env` in the repository root and fill in the providers you use. The rebuild defaults to Qwen:

```ini
# Provider selection
LLM_PROVIDER=qwen
EMBEDDING_PROVIDER=
VIDEO_PROVIDER=gemini
SPATIAL_PROVIDER=gemini
TRANSCRIBE_PROVIDER=openai
TTS_PROVIDER=none

# Provider credentials and compatible endpoints
DASHSCOPE_API_KEY=your_dashscope_key
# QWEN_APIKEY is accepted when DASHSCOPE_API_KEY is unset.
OPENAI_API_KEY=
GEMINI_API_KEY=your_gemini_key
OLLAMA_BASE_URL=http://localhost:11434

# Optional per-capability model overrides
LLM_TEXT_MODEL=
LLM_SYNTHESIS_MODEL=
LLM_VISION_MODEL=
LLM_EMBEDDING_MODEL=
LLM_EMBEDDING_DIM=
LLM_TRANSCRIBE_MODEL=
LLM_TTS_MODEL=
LLM_VIDEO_MODEL=

# Semantic retrieval
# Leave blank for the repository-root Storage/chroma directory; otherwise use an absolute path.
CHROMA_PERSIST_DIR=
SEMANTIC_SEARCH_TOP_K=5

# Database
MONGODB_URI=mongodb://localhost:27017
TIMEZONE=America/Los_Angeles
# Leave blank for the repository root; otherwise use an absolute path.
MEDIA_ROOT=

# Gemini perception support
GEMINI_VIDEO_MODEL=gemini-3-flash-preview
GEMINI_VIDEO_FALLBACK_MODELS=gemini-2.5-flash
GEMINI_VIDEO_MAX_RETRIES=3
GEMINI_VIDEO_RETRY_BASE_SECONDS=4
VIDEO_ANALYSIS_TIMEOUT_SECONDS=300
GEMINI_SPATIAL_MODEL=gemini-2.5-flash

# Safety and alert prototype
SAFETY_AGENT_ENABLED=true
SAFETY_ALERT_MIN_SEVERITY=medium
FALL_ALERT_RECIPIENT_EMAIL=<caretaker-email>

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

See `.env.example` for the complete configuration surface, including OSS video-bridge, safety, Firebase, and geofence settings.

## Running the System

### 1. Start the backend API and web UI

```powershell
uvicorn Blue_dream_agents.api:app --reload
```

This serves:

- web UI at `http://localhost:8000`
- assistant query endpoint at `POST /query`
- static media under `/capture/*` and `/storage/*`

MongoDB stores media references as portable `Storage/...` or `Capture/...` paths.
The backend resolves those paths beneath `MEDIA_ROOT` and exposes URL paths through
the static mounts above. Leave `MEDIA_ROOT` blank unless runtime media lives under
a different absolute root.

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

- **`Blue_dream_agents/`**: FastAPI backend, unified provider client, assistant orchestration, memory retrieval, safety agent, and alert service
- **`Capture/`**: Camera ingestion, audio capture, video queueing, and fall detection
- **`UI/`**: Static patient web UI served by FastAPI
- **`Mobile/`**: Expo React Native patient app
- **`Storage/`**: Runtime media, highlighted images, and local Chroma persistence
- **`Demo/`**: Demo images, GIFs, architecture visuals, and evaluation assets
- **`benchmarks/`**: Reference benchmarking utilities and architecture notes

## Prototype Boundaries and Operational Notes

- Memoria is a functional prototype, not a medical device or emergency-response replacement.
- Qwen is the default provider profile; live Qwen capability validation and ASR/video wiring are deliberately scoped to spec 0005.
- The OpenAI transcription fallback is offline-tested but not a live validation gate for spec 0003.
- Remote Firebase push delivery is scaffolded but still requires final Firebase/device validation for production-style Android push.
- Expo Go on Android SDK 54 does not support remote push notifications; use an EAS development build for real FCM testing.
- `Capture/camera_feed.py` currently uses hardcoded camera indices `[1, 2]`.
- Room assumptions are currently fixed to `0 = Bedroom` and `1 = Living Room`.
- Gmail alerts require local credential artifacts under `Blue_dream_agents/Tools/` and `FALL_ALERT_RECIPIENT_EMAIL` in `.env`.
- Chroma may recreate only the active provider collection when its metadata is invalid; sibling provider collections are preserved.
- `Storage/` contains runtime media and should be treated as generated data, not source code.
- `Storage/`, `Proof/`, and local credential files are Git-ignored, but `/storage` is still served by the development backend. Keep the backend on a trusted local network until authentication and media access controls are added.

## Roadmap Snapshot

Current overhaul status is tracked in [`docs/FEATURE_STATUS.md`](docs/FEATURE_STATUS.md).

- **Validated offline**: unified provider resolution/client contracts, structured JSON hardening, provider-specific semantic indexes, media paths, and existing backend contracts.
- **Next**: capture-pipeline repair (0004), followed by the first live Qwen end-to-end gate (0005).
- **Planned**: durable memory, lifecycle, proactive turns, voice, submission polish, and the OpenAI provider flip.

## Historical Kaggle Project Description

The following section describes the pre-rebuild Gemma submission and is retained as project history; it is not the current runtime or setup guide.

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
