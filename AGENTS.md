# AGENTS.md Baseline (As-Is) for Blue-Dream

## Purpose + Scope
- This document is for autonomous coding agents first, with humans as secondary readers.
- It defines the **current** state of the project (including quirks and inconsistencies).
- Treat this as an operational baseline for safe edits before the planned overhaul.
- This file was previously empty.

## Overhaul Execution Baseline
- The project is now in an active overhaul phase.
- `PLANS.md` is the execution roadmap for the overhaul.
- Future agents should consult both:
  - `AGENTS.md` for the current implementation baseline
  - `PLANS.md` for planned feature sequence and status
- Overhaul implementation proceeds one feature at a time unless explicitly coordinated.
- After each completed feature:
  - validate it
  - commit it
  - update `PLANS.md`
  - update `AGENTS.md`

## Target Overhaul Direction
- The patient web app remains a primary surface.
- The Expo React Native patient mobile app under `Mobile/` is now an active second patient surface, supporting chat, alert list/detail, geofence guidance, and push-notification scaffolding.
- MongoDB remains the source of truth for memory events.
- ChromaDB is now the active vector index for semantic memory search.
- Gemma 4 E2B through local Ollama is now the active text and current-image reasoning runtime for:
  - routing
  - semantic synthesis
  - semantic evidence judging
  - current room snapshot object-presence checks
  - patient-facing text responses
- Nova/Bedrock remains in the repository for legacy/future paths, including:
  - optional legacy semantic embeddings behind `EMBEDDING_PROVIDER=bedrock`
  - voice experiments
- Gemini remains the planned exception for:
  - long-form video understanding
  - image bounding/localization

## Platform Assumptions
- Primary development environment: Windows + PowerShell.
- Python project with local execution style (no formal packaging config in repo root).
- `Blue_dream_agents/`, `Blue_dream_agents/llm/`, `Blue_dream_agents/Tools/`, `Blue_dream_agents/voice/`, and `Capture/` are all Python packages (each has `__init__.py`).
- MongoDB is expected to run locally unless `MONGODB_URI` overrides it.
- MongoDB uses a short server-selection timeout so startup/index checks fail quickly when the local server is unavailable.

## Canonical Runtime Commands
- Start backend API + UI static hosting:
```powershell
uvicorn Blue_dream_agents.api:app --reload
```
- Start backend API accessible from LAN/mobile (bind all interfaces):
```powershell
uvicorn Blue_dream_agents.api:app --reload --host 0.0.0.0
```
- Start capture pipeline:
```powershell
python Capture/camera_feed.py
```
- Access UI:
  - `http://localhost:8000`
- Start mobile app (Metro bundler):
```powershell
cd Mobile
npx expo start
```

## Critical Interfaces (Do Not Break)

### 1) API Query Contract
- Endpoint: `POST /query`
- Request body:
```json
{ "query": "Where are my keys?" }
```
- Optional short-term conversation request body:
```json
{ "query": "What room was that in?", "session_id": "browser-session-id" }
```
- Response model (`JeevesResponse`) shape:
```json
{
  "response_type": "search_result | activity | general",
  "text": "string",
  "image_path": "string | null",
  "data": "object | null"
}
```
- `UI/script.js` assumes this schema and directly renders `text` + optional `image_path`.
- `session_id` must not change the response shape; it only enables in-process chat context.

### 1b) Conversation Session Memory Contract
- Endpoint: `POST /conversation/reset`
- Request body:
```json
{ "session_id": "browser-session-id" }
```
- Response body:
```json
{ "ok": true }
```
- Conversation memory is process-local, in-memory, and short-term only.
- It keeps recent UI chat turns for follow-up query rewriting and answer context.
- It is not MongoDB patient memory, is not embedded in ChromaDB, and resets through the UI New Chat action or backend process restart.

### 1c) Mobile Alert Contract
- Device registration endpoint:
```json
POST /devices/register
{ "device_id": "phone-id", "platform": "android", "push_provider": "fcm", "push_token": "token", "role": "patient" }
```
- Patient alert list endpoint:
```json
GET /alerts/patient?status=open
```
- Alert detail endpoint:
```json
GET /alerts/{alert_id}
```
- Alert acknowledgement endpoint:
```json
POST /alerts/{alert_id}/ack
{ "action": "ok | returning | dismissed" }
```
- Alert detail responses are JSON-safe and include fields such as `alert_id`, `event_id`, `hazard_type`, `severity`, `title`, `body`, `detailed_explanation`, `recommended_action`, `room_name`, `image_path`, `original_image_path`, `highlight_target`, `highlight_status`, `status`, and `deep_link`.
- Mobile push payloads use `memoria://alerts/{alert_id}` deep links.

### 1d) Geofence Compatibility Contract
- Current geofence endpoint:
```json
GET /geofence/current
```
- Update geofence endpoint:
```json
PUT /geofence/current
{ "home_lat": 0.0, "home_lng": 0.0, "radius_meters": 100 }
```
- Mobile geofence event endpoint:
```json
POST /geofence/events
{ "event_type": "exit | enter", "latitude": 0.0, "longitude": 0.0, "device_id": "phone-id" }
```
- The first geofence implementation is hackathon-simple: backend stores one default boundary, mobile checks location locally, and Google Maps navigation is launched by the mobile app.

### 2) Event Ingestion Contract (MongoDB)
- Database: `dementia_assistance`
- Collection: `events`
- Canonical event model: `Blue_dream_agents/memory_schema.py::MemoryEvent`
- New consolidator writes include:
  - `_id` (Mongo `ObjectId`)
  - `event_id`
  - `timestamp`
  - `room_number`
  - `room_name`
  - `video_description`
  - `room_objects`
  - `audio_transcript`
  - `screenshot_path`
  - `video_path`
  - `audio_path`
  - `semantic_text`
  - `danger_candidate`
  - `scene_end_state`
  - `observed_hazards`
  - `uncertainties`
  - `safety_assessment`
- Legacy Mongo docs are still supported through read-time normalization:
  - `event_id` falls back to `_id`
  - `room_name` falls back to the shared room map
  - `semantic_text` is built from the event fields if absent
- Active retrieval paths in `time_agent.py` and `object_detector.py` now normalize Mongo docs through `MemoryEvent` before reasoning over them.
- Runtime index setup creates non-unique MongoDB indexes for `timestamp`, `room_number + timestamp`, `event_id`, and `video_path`.
- `video_path` is used for application-level ingestion idempotency; reprocessing the same video path should skip duplicate Mongo inserts and may re-run Chroma indexing for the existing event.

### 3) Static Path Conventions
- API mounts:
  - `/capture/*` -> `Capture/`
  - `/storage/*` -> `Storage/`
- UI rewrites returned image paths to these mount conventions.
- Keep these compatible unless migration is explicit and coordinated.

### 4) Room Mapping Assumptions
- Shared logical mapping used across capture/time/object logic:
  - `0 = Bedroom`
  - `1 = Living Room`
- If room IDs/names change, update all modules relying on this mapping.

## Current Architecture Map
- Capture + ingestion pipeline:
  - `Capture/camera_feed.py`
  - -> `Capture/video_processing_queue.py` (`VideoProcessingQueue`)
  - -> `Blue_dream_agents/consolidator.py` (`consolidator_agent`)
  - -> `Blue_dream_agents/memory_schema.py` (`MemoryEvent` normalization/serialization)
  - -> `Blue_dream_agents/safety_agent.py` (Gemma safety judge for factual hazard observations)
  - -> `Blue_dream_agents/alert_service.py` (patient-actionable alert persistence and optional FCM delivery)
  - -> `Blue_dream_agents/db_client.py` (shared MongoDB singleton)
  - -> MongoDB `dementia_assistance.events`
  - -> MongoDB `dementia_assistance.safety_alerts` for actionable safety alerts
  - -> `Blue_dream_agents/semantic_search.py` / `Blue_dream_agents/vector_store.py`
  - -> ChromaDB collection `memory_events`
- Assistant request pipeline:
  - `Blue_dream_agents/api.py` (`POST /query`)
  - -> `Blue_dream_agents/conversation_memory.py` for optional in-process session context when `session_id` is supplied
  - -> `Blue_dream_agents/jeeves.py` (query router + semantic judge through local Gemma/Ollama)
  - -> `Blue_dream_agents/time_agent.py`, `Blue_dream_agents/object_detector.py`, and `Blue_dream_agents/semantic_search.py`
  - -> `Blue_dream_agents/db_client.py` (shared MongoDB singleton used by all retrieval agents)
  - -> `Blue_dream_agents/gemini_spatial.py` for automatic single-box screenshot highlighting after a current-state object visual match
  - -> `Blue_dream_agents/time_agent.py::get_time_window_context` for semantic-grounding follow-up around a trusted anchor event
  - -> `Blue_dream_agents/memory_schema.py` for canonical event reads
  - -> `Blue_dream_agents/llm/settings.py`
  - -> `Blue_dream_agents/llm/model_registry.py`
  - -> `Blue_dream_agents/llm/ollama_runtime.py`
  - -> `Blue_dream_agents/llm/bedrock_client.py`
  - -> `Blue_dream_agents/llm/embedding_client.py`
  - -> `Blue_dream_agents/llm/prompt_context.py`
  - -> `Blue_dream_agents/llm/strands_runtime.py`
  - -> `Blue_dream_agents/prompt_budget.py` for compacting large evidence prompts
- Frontend:
  - `UI/index.html`, `UI/script.js`, `UI/styles.css`
  - `UI/script.js` posts to `/query` and renders optional images.
- Mobile patient app (`Mobile/`):
  - Expo React Native with Expo Router (file-based routing).
  - `Mobile/app/index.js` — Chat screen mirroring web UI behavior: `POST /query`, `POST /conversation/reset`, stable `session_id`, image rendering.
  - `Mobile/app/alerts/index.js` — Alert list screen (`GET /alerts/patient?status=open`).
  - `Mobile/app/alerts/[id].js` — Alert detail + acknowledgement actions (`GET /alerts/{id}`, `POST /alerts/{id}/ack`).
  - `Mobile/app/geofence.js` — Geofence screen with fallback home coordinates and "Guide me home" Google Maps navigation.
  - `Mobile/lib/api.js` — API client with image-path rewriting (`/Storage/` and `/Capture/` to backend URLs).
  - `Mobile/lib/session.js` — AsyncStorage-backed stable session ID.
  - `Mobile/lib/device.js` — AsyncStorage-backed stable device ID.
  - `Mobile/lib/notifications.js` — Android notification channel setup, permission request, push token acquisition, `POST /devices/register`, and local test-notification helper.
  - `Mobile/app/_layout.js` — Root Stack layout with Memoria header, New Chat button, Alerts button, notification-init effect, and deep-link routing (`memoria://alerts/{alert_id}`).
  - Deep-link scheme `memoria://` configured in `Mobile/app.json`.
  - Push provider currently set to `"expo"` for Expo Go prototype mode; `"fcm"` can be swapped in later for EAS dev build + Firebase.
  - Dev-only test-notification button on geofence screen (hidden in production builds via `__DEV__`).

## Source-of-Truth Files vs Legacy/Archive

### Active Source-of-Truth (default edit targets)
- `Blue_dream_agents/api.py`
- `Blue_dream_agents/conversation_memory.py`
- `Blue_dream_agents/db_client.py`
- `Blue_dream_agents/jeeves.py`
- `Blue_dream_agents/time_agent.py`
- `Blue_dream_agents/object_detector.py`
- `Blue_dream_agents/gemini_spatial.py`
- `Blue_dream_agents/memory_schema.py`
- `Blue_dream_agents/llm/settings.py`
- `Blue_dream_agents/llm/model_registry.py`
- `Blue_dream_agents/llm/ollama_runtime.py`
- `Blue_dream_agents/llm/bedrock_client.py`
- `Blue_dream_agents/llm/embedding_client.py`
- `Blue_dream_agents/llm/prompt_context.py`
- `Blue_dream_agents/llm/strands_runtime.py`
- `Blue_dream_agents/prompt_budget.py`
- `Blue_dream_agents/safety_agent.py`
- `Blue_dream_agents/alert_service.py`
- `Blue_dream_agents/consolidator.py`
- `Blue_dream_agents/semantic_search.py`
- `Blue_dream_agents/vector_store.py`
- `Blue_dream_agents/video_agent.py`
- `Blue_dream_agents/audio_transcribe.py`
- `Blue_dream_agents/timezone_utils.py`
- `Blue_dream_agents/Tools/dementia_email.py`
- `Capture/camera_feed.py`
- `Capture/video_processing_queue.py`
- `Capture/audio_capture.py`
- `UI/index.html`
- `UI/script.js`
- `UI/styles.css`
- `Mobile/app/_layout.js`
- `Mobile/app/index.js`
- `Mobile/app/alerts/index.js`
- `Mobile/app/alerts/[id].js`
- `Mobile/app/geofence.js`
- `Mobile/lib/api.js`
- `Mobile/lib/session.js`
- `Mobile/lib/device.js`
- `Mobile/lib/notifications.js`
- `Mobile/constants/theme.js`

### Planning Source-of-Truth
- `PLANS.md` is the source of truth for overhaul sequencing and feature status.
- Code files remain the source of truth for current runtime behavior.

### Legacy / Non-Authoritative (avoid unless task explicitly requires)
- `Blue_dream_agents/time-agent copy.py`
- `Blue_dream_agents/sam3_api.py` (machine-specific SAM3 paths, CWD side effects, GPU load at import; replaced by `gemini_spatial.py`)
- `Blue_dream_agents/Tools/object_highlight.py` (broken: references undefined variable, non-existent OpenAI model `gpt-image-1.5`; replaced by `gemini_spatial.py`)
- `Blue_dream_agents/voice/` subpackage (`sonic_session.py`, `tool_adapter.py`) - Nova Sonic bidirectional streaming voice experiment; not on active runtime path
- `Blue_dream_agents/test_image_object_pipeline.py` - standalone validation script for the vision + Gemini spatial pipeline
- Training/experimental artifacts in `Capture/trained-weights/training_code.py`
- Top-level reference/placeholder scripts: `main.py` (trivial placeholder), `nova_sonic_tool_use_reference.py`, `spatial_understanding.py`
- `test.ipynb` - experimentation notebook
- `yolo11n.pt` at repo root (unused; fall detection uses `Capture/trained-weights/best.pt`)
- Notebook and demo/proof materials unless task is documentation/demo related.

### Support / Test / Demo Directories (not source-of-truth)
- `benchmarks/` - `benchmark_current_memory.py` (performance testing) and `architecture.md` (reference notes)
- `Blue_dream_agents/test_data/` - contains `Recording.m4a` for transcription testing
- `Demo/` - demonstration media files (architecture diagram, screenshots, confusion matrices, GIF)
- `Proof/` - proof-of-concept recordings and media (gitignored)
- `text_scripts_for_video/` - narration and script text for demo videos
- `System/` - empty directory (reserved)
- `Storage/` - runtime data (screenshots, video recordings, audio recordings, ChromaDB persistence, highlighted outputs); gitignored; not source code

## Environment + Secrets
- Required keys in `.env` for core behavior:
  - `GEMINI_API_KEY`
  - `OPENAI_TRANSCRIBE_API_KEY` for the current ingestion-time transcription path
  - Optional: `MONGODB_URI`
  - Optional for Phase 1 text reasoning: `LOCAL_LLM_PROVIDER`, `OLLAMA_BASE_URL`, `GEMMA_TEXT_MODEL`
  - Optional for local image reasoning: `GEMMA_VISION_MODEL`
  - Optional for local semantic embeddings: `EMBEDDING_PROVIDER`, `LOCAL_EMBEDDING_MODEL`, `CHROMA_EMBEDDING_DIMENSION`
  - Optional for safety/alert demo: `SAFETY_AGENT_ENABLED`, `SAFETY_ALERT_MIN_SEVERITY`
  - Optional for Firebase push: `FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_ANDROID_PACKAGE`
- Optional for geofence demo: `PATIENT_HOME_LAT`, `PATIENT_HOME_LNG`, `PATIENT_GEOFENCE_RADIUS_METERS`
- Mobile-only:
  - `EXPO_PUBLIC_API_BASE_URL` in `Mobile/.env` (e.g., `http://192.168.1.112:8000`)
  - No other mobile keys required for Expo Go chat/alert/geofence development
- Required only for legacy Nova embeddings when `EMBEDDING_PROVIDER=bedrock`: `AWS_BEARER_TOKEN_BEDROCK` or standard AWS credentials/profile
- Optional Nova overrides:
  - `LOCAL_LLM_PROVIDER` (defaults to `ollama`)
  - `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`)
  - `GEMMA_TEXT_MODEL` (defaults to `gemma4:e2b`)
  - `GEMMA_VISION_MODEL` (defaults to `GEMMA_TEXT_MODEL`, then `gemma4:e2b`)
  - `NOVA_ROUTER_MODEL`
  - `NOVA_SYNTHESIS_MODEL`
  - `NOVA_VISION_MODEL`
  - `NOVA_VISION_FALLBACK_MODEL`
  - `NOVA_EMBEDDING_MODEL`
  - `EMBEDDING_PROVIDER` (defaults to `ollama`)
  - `LOCAL_EMBEDDING_MODEL` (defaults to `nomic-embed-text`)
  - `CHROMA_EMBEDDING_DIMENSION` (defaults to `768`)
  - `GEMINI_SPATIAL_MODEL`
  - `GEMINI_VIDEO_MODEL` (defaults to `gemini-3-flash-preview` for full-video analysis)
  - `GEMINI_VIDEO_FALLBACK_MODELS`
  - `GEMINI_VIDEO_MAX_RETRIES`
  - `GEMINI_VIDEO_RETRY_BASE_SECONDS`
  - `BEDROCK_AWS_REGION`
  - `BEDROCK_API_KEY_REGION`
  - `CHROMA_PERSIST_DIR`
  - `CHROMA_COLLECTION_NAME`
  - `SEMANTIC_SEARCH_TOP_K`
  - `SAFETY_AGENT_ENABLED`
  - `SAFETY_ALERT_MIN_SEVERITY`
  - `FIREBASE_PROJECT_ID`
  - `FIREBASE_CREDENTIALS_PATH`
  - `FIREBASE_ANDROID_PACKAGE`
  - `PATIENT_HOME_LAT`
  - `PATIENT_HOME_LNG`
  - `PATIENT_GEOFENCE_RADIUS_METERS`
- Current local Gemma/Ollama defaults/expectations:
  - `/query` text routing, text synthesis, structured text decisions, and current room snapshot object checks use direct Ollama HTTP through `Blue_dream_agents/llm/ollama_runtime.py`
  - `LOCAL_LLM_PROVIDER=ollama` is the default
  - `GEMMA_TEXT_MODEL=gemma4:e2b`
  - `GEMMA_VISION_MODEL` defaults to `gemma4:e2b`
  - `OLLAMA_BASE_URL=http://localhost:11434`
  - local semantic embeddings use Ollama `/api/embed`
  - `EMBEDDING_PROVIDER=ollama`
  - `LOCAL_EMBEDDING_MODEL=nomic-embed-text`
  - `CHROMA_EMBEDDING_DIMENSION=768`
  - Ollama structured calls use JSON mode, disable thinking where supported, strip JSON fences, extract JSON from noisy responses, validate with Pydantic, and retry once with stricter JSON-only instructions
  - Ollama multimodal structured calls send base64 image input through `/api/chat`
  - Bedrock credentials are not required for general `/query` text routing, response synthesis, or current snapshot object checks
- Current Bedrock/Nova defaults/expectations:
  - the active Nova setup now standardizes `BEDROCK_AWS_REGION=us-east-1`
  - API-key auth path falls back to a Bedrock-supported API-key region if needed
  - Nova 2 Lite should be referenced through the inference-profile style model ID, for example `us.amazon.nova-2-lite-v1:0`
  - Nova embeddings use `amazon.nova-2-multimodal-embeddings-v1:0` only when `EMBEDDING_PROVIDER=bedrock`
  - Gemini spatial localization defaults to `GEMINI_SPATIAL_MODEL`, then `GEMINI_VIDEO_MODEL`, then `gemini-2.5-flash`
  - local Chroma persistence defaults to `Storage/chroma`
  - OpenAI is still used only for ingestion-time audio transcription through `OPENAI_TRANSCRIBE_API_KEY`
  - `OPENAI_API_KEY` remains a backward-compatible fallback for transcription only
  - `OPENAI_BASE_URL` is not part of the active runtime contract
- Gmail integration expects:
  - `Blue_dream_agents/Tools/credentials.json`
  - Generated token: `Blue_dream_agents/Tools/token.pickle`
- Never commit secrets, tokens, credential files, or local auth artifacts.

## Known Quirks Agents Must Respect
- `README.md` may lag the active Nova/OpenAI split if documentation updates are incomplete; verify against source files before changing env guidance.
- `time_agent.py` now routes through structured Strands prompts rather than an exported SDK agent object.
- `semantic_text` is now the canonical event-text representation and is the active local embedding input.
- `/query` no longer relies on a generic tool-selection prompt for semantic/time routing; `jeeves.py` now performs explicit query routing and an LLM-based semantic evidence judgment step through local Gemma/Ollama before deciding on semantic-only answering, semantic-plus-time grounding, direct time reasoning, or insufficient evidence.
- `/query` can use optional in-process conversation context when the client supplies `session_id`; follow-up messages are rewritten into standalone queries before routing, while clients without `session_id` retain standalone behavior.
- Conversation session memory is not durable patient memory and must not be stored in MongoDB, indexed in ChromaDB, or used as monitoring evidence. Object/time/semantic tools receive the resolved standalone query; full conversation history is only included for rewrite/general-chat context.
- `consolidator.py` persists partial events when either video analysis or audio transcription fails; one failed modality should not discard the other.
- `video_agent.py` result fields have safe defaults: an empty description and an empty object list.
- `video_agent.py` now also returns factual safety-observation fields; Gemini provides observations, while Gemma owns the final safety warning decision.
- `video_agent.py` defaults to `gemini-3-flash-preview` for full-video analysis and falls back to `gemini-2.5-flash` unless `GEMINI_VIDEO_FALLBACK_MODELS` overrides it.
- `video_agent.py` retries transient Gemini video-analysis failures such as 503 high-demand responses before falling back to partial ingestion.
- `safety_agent.py` is conservative: missing, ambiguous, or low-confidence danger evidence should store uncertainty rather than alerting.
- `alert_service.py` stores actionable patient alerts even when FCM is not configured; delivery status may be `no_devices`, `not_configured`, `sent`, or `failed`.
- `alert_service.py` attempts best-effort Gemini hazard highlighting for alert detail images; `image_path` is the highlighted output when generated and falls back to the original screenshot.
- Firebase service account JSON files must remain gitignored and must not be committed.
- `memory_schema.py` omits empty semantic-text sections instead of embedding literal `"None"` / `"none"` sentinel text.
- Chroma reset now raises on filesystem reset failures instead of silently continuing after an incomplete delete.
- Active Gemma/Nova prompts now share `Blue_dream_agents/llm/prompt_context.py` so monitoring evidence is interpreted as fixed home CCTV / room-microphone data rather than first-person or body-cam footage.
- Generic unlabeled person references inside stored monitoring evidence are now interpreted as the patient by default; explicitly named or clearly identified other people remain distinct.
- `Capture/camera_feed.py` currently uses hardcoded camera indices `[1, 2]`.
- `Capture/camera_feed.py` has a hardcoded fall-alert recipient email.
- `Blue_dream_agents/sam3_api.py` remains a legacy module with local-machine-specific SAM3 root/CWD behavior and is no longer on the active object-highlighting path.
- Direct Ollama HTTP is now the active text and current-image object reasoning path.
- Direct Ollama `/api/embed` with `nomic-embed-text` is now the active semantic embedding path.
- Bedrock-native access remains in the codebase for optional legacy Nova embeddings and voice paths.
- Ingestion-time audio transcription still uses OpenAI `gpt-4o-transcribe`; this is separate from the Bedrock-native Nova runtime and remains slated for Feature 6 migration.
- Nova 2 Lite requests may fail with the bare model ID `amazon.nova-2-lite-v1:0`; the working Bedrock path is the inference-profile style ID such as `us.amazon.nova-2-lite-v1:0`.
- API-key auth is region-limited, so the runtime falls back to a supported API-key region when standard AWS credentials are not present.
- Production Chroma persistence now assumes a 768-dimensional local semantic collection under `Storage/chroma`; if the persisted collection has the wrong dimension/provider/model or contains legacy smoke-test artifacts, the runtime may reset the local Chroma store before reuse.
- Semantic retrieval no longer depends on Nova embeddings by default. If local Ollama embedding access is unavailable, semantic `/query` requests should degrade to an insufficient-evidence response rather than crashing the API.
- Vector-store smoke tests must never use the production Chroma path or the `memory_events` collection.
- Some imports used by code are not represented in `requirements.txt` (for example Gmail auth client libs).
- Repository includes real `Storage/` media artifacts; treat them as runtime data, not source code.
- Object search now checks the latest snapshot for each room first; if the object is visually recognized in a current room image, the runtime attempts Gemini highlighting automatically and falls back to a text-only current-state answer if localization fails.
- Historical last-known-location reasoning is now only used when the object is not visually recognized in any current room snapshot.
- Gemini spatial responses may arrive either as object-style JSON (`{"box_2d": [...], "label": ...}`) or array-style output (`[y1, x1, y2, x2, label]`); `gemini_spatial.py` now normalizes both formats.
- `timezone_utils.py` hardcodes `America/Los_Angeles` (Pacific time) with no environment variable override; all event timestamps and "now" references use this zone.
- `python-dotenv` is listed in `requirements.txt` but is not used; `llm/settings.py` has its own custom `.env` parser that supports Windows `SET` prefix stripping.
- `embedding_client.py` uses synchronous `urllib.request` for Ollama embedding calls while `ollama_runtime.py` uses async `httpx`; embedding calls block the event loop when called from async code paths.
- `video_agent.py` creates an unused global `genai.Client` at module import time (line 14) in addition to the instance client in `__init__`; harmless but wasteful side effect.
- The UI is branded as "Memoria" (page title: "Memoria - Personal Assistant", header: "Memoria"); this is the patient-facing product name.
- `Capture/camera_feed.py` maps camera index 1 to room 0 (Bedroom) and camera index 2 to room 1 (Living Room); resolution is 1920x1080 at 20 FPS via DirectShow.
- Fall detection uses a 3.5-second stability window before triggering an alert; the YOLO model uses a 0.50 confidence threshold.
- The UI is branded as "Memoria" (page title: "Memoria - Personal Assistant", header: "Memoria"); this is the patient-facing product name.
- `Mobile/.env` uses `EXPO_PUBLIC_API_BASE_URL` for the backend LAN IP. Metro reads env at startup; changes require a Metro restart.
- Expo Go on Android does not support remote push notifications for SDK 54+. Local notifications and deep-link routing work for testing, but real FCM delivery requires an EAS development build.
- Mobile push provider is `"expo"` in prototype mode and should be switched to `"fcm"` when building with EAS + Firebase.
- Mobile image path rewriting in `lib/api.js` mirrors the web UI logic: `/Storage/` and `/Capture/` are prefixed with `EXPO_PUBLIC_API_BASE_URL`.
- Mobile geofence screen uses hardcoded fallback coordinates (`34.034992564747604, -118.28252676933066`) when the backend geofence is not configured.
- Dev-only test-notification button on the geofence screen is gated by `__DEV__` and should be removed before the final demo.

## Safe Edit Rules (Project-Specific)
- If changing response models or API output fields, update both:
  - backend schemas/serialization
  - `UI/script.js` rendering assumptions
- If changing room constants or camera-room mapping, propagate updates through:
  - capture pipeline
  - time agent queries
  - object detector logic
- Preserve `/storage` and `/capture` compatibility unless explicit migration is requested.
- Do not refactor based only on README assumptions; verify against active source files.
- Prefer minimal targeted changes over cross-cutting rewrites in this baseline phase.

## Overhaul Workflow Rules
- Implement one feature at a time unless explicitly coordinated.
- Before starting a feature, review its section in `PLANS.md`.
- After completing a feature:
  - validate it
  - commit it
  - update `PLANS.md`
  - update `AGENTS.md`
- Do not mark planned architecture as implemented until code and validation are complete.

## Planned Feature Sequence
- Phase 1: Gemma/Ollama Runtime (validated)
- Phase 2: Local Semantic Retrieval (validated)
- Phase 2.5: Conversation Session Memory (validated)
- Phase 2.6: Memory Stack Audit Remediation (validated)
- Phase 3: Gemma Safety Agent
- Phase 4: Alert Delivery
- Phase 5: Mobile Patient App
- Phase 6: Caretaker Dashboard
- Phase 7: Demo and Submission Package
- Phase 8: Local Gemma Vision Prototype

## Validation Checklist for Future Agent Work
- For touched Python files:
  - run a minimal syntax/type sanity pass appropriate to the change.
- For API-touching changes:
  - run backend and smoke-test `POST /query`.
  - verify `{ "query": "..." }` remains valid if adding optional request fields.
- For ingestion changes:
  - verify duplicate `video_path` handling does not create a second Mongo event.
  - verify partial video/audio failures still persist an event.
- For capture-pipeline changes:
  - verify queue handoff (`camera_feed` -> `VideoProcessingQueue` -> `consolidator_agent`) remains intact.
  - verify Mongo insert payload still contains expected event fields.
- For UI changes:
  - verify chat rendering still handles `text` + optional `image_path`.
  - verify `/storage` and `/capture` path rewriting still works.
- For retrieval changes:
  - verify large event lists are prompt-budgeted before LLM calls.

## Documentation Update Test Cases (This Change)
- Confirm commands in this doc match executable entrypoints in repository files.
- Confirm listed API and event-schema fields match current code paths.
- Confirm quirks listed here are present in current implementation.
- Confirm this change modifies documentation only and does not alter runtime behavior.

## Baseline Note
- This AGENTS file intentionally documents the present implementation and quirks.
- Feature 2 canonical memory-event schema is now part of the current implementation baseline.
- Feature 3 semantic search foundation is now part of the current code baseline.
- Feature 5 Gemini spatial localization replacement is now part of the current code baseline.
- Feature 5 has been live-validated against a stored screenshot with successful Gemini-generated highlighting output under `Storage/highlighted/`.
- Phase 1 Gemma/Ollama text runtime is now part of the current implementation baseline.
- Phase 2 local semantic retrieval through Ollama `nomic-embed-text` is now part of the current implementation baseline.
- Short-term browser-session conversation memory is now part of the current `/query` implementation baseline.
- Audit remediation for Mongo indexes, ingestion idempotency, partial-result persistence, prompt budgeting, safer schema serialization, and Chroma reset handling is now part of the current implementation baseline.
- Expect this file to be revised as the planned architecture overhaul proceeds.
