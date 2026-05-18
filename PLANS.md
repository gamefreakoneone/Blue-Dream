# Project Memoria Gemma 4 Good Hackathon Plan

## Purpose
- This file is the active execution roadmap for Project Memoria's Gemma 4 Good Hackathon pivot.
- It replaces the older Nova-first overhaul plan.
- Future work should proceed one phase at a time, in order, unless explicitly coordinated.
- Each phase describes:
  - the current situation
  - what needs to be done
  - how the project moves forward after that phase

## Core Direction
- Project Memoria is now being positioned as a Gemma-powered dementia recall and safety agent.
- Gemma 4 E2B through Ollama is the target primary reasoning layer for:
  - query routing
  - memory answer synthesis
  - semantic evidence judging
  - safety warning decisions
  - patient-facing explanations
- Gemini can remain as a perception tool for reliable full-video understanding and spatial localization where needed.
- Gemini should not own the final autonomous safety decision in the hackathon architecture.
- Nova/Bedrock code remains part of the current repository baseline, but it is no longer the target hackathon runtime.
- The patient web app, FastAPI backend, MongoDB event store, ChromaDB semantic index, and capture pipeline remain valuable project foundations.

## Execution Rules
1. Work on only one phase at a time.
2. Before starting a phase, read that phase in this file and check `AGENTS.md` for the current implementation baseline.
3. Implement the phase with minimal targeted changes.
4. Validate the phase with the listed checks or an equivalent focused smoke test.
5. After completing a phase:
   - update this file with status, decisions, and notes
   - update `AGENTS.md` if architecture, runtime commands, interfaces, env vars, or known quirks changed
   - commit the completed phase
6. Do not mark a planned runtime replacement as complete until code and validation prove it.

## Stable Interfaces To Preserve
- `POST /query`
- Request body:
```json
{ "query": "Where are my keys?" }
```
- Optional request body for short-term conversation context:
```json
{ "query": "What room was that in?", "session_id": "browser-session-id" }
```
- Response model shape:
```json
{
  "response_type": "search_result | activity | general",
  "text": "string",
  "image_path": "string | null",
  "data": "object | null"
}
```
- `POST /conversation/reset` accepts `{ "session_id": "browser-session-id" }` and clears only in-process chat context.
- Static media mounts:
  - `/capture/*` maps to `Capture/`
  - `/storage/*` maps to `Storage/`
- MongoDB source of truth:
  - database: `dementia_assistance`
  - collection: `events`
- ChromaDB remains a semantic index only, not the source of truth.

## Phase Status Legend
- `Planned`
- `In Progress`
- `Validated`
- `Committed`
- `Blocked`

## Phase 0: Roadmap Reset
**Status:** Validated

### Current Situation
- `PLANS.md` previously described a Nova-first overhaul.
- The active codebase already includes useful completed foundations:
  - camera capture and room event recording
  - video processing queue
  - Gemini video descriptions
  - canonical MongoDB memory events
  - ChromaDB semantic search
  - object search and image highlighting
  - FastAPI-served patient web UI
  - initialized Android app under `Mobile/`
- `AGENTS.md` still documents the current implementation baseline, including Nova/Bedrock code paths.

### What We Will Do
- Replace the old Nova-first plan with this Gemma-first phase roadmap.
- Keep `AGENTS.md` as the current implementation baseline until individual phases actually change the code.
- Make the next engineering target clear: Phase 1 starts by moving the text reasoning path to local Gemma through Ollama.

### Moving Forward
- Phase 0 is complete once this file clearly tells a fresh agent where the project is going and what phase to start next.
- The next fresh context window should begin with Phase 1.

### Validation
- Confirm `PLANS.md` no longer instructs agents to continue the Nova-first roadmap.
- Confirm Phase 1 has enough context to start implementation without rereading the prior planning conversation.

## Phase 1: Gemma/Ollama Runtime
**Status:** Validated

### Current Situation
- `/query` text reasoning now routes through local Gemma via Ollama by default.
- The implementation uses direct Ollama HTTP calls from `Blue_dream_agents/llm/ollama_runtime.py`.
- `Blue_dream_agents/llm/strands_runtime.py` remains as the shared call surface, dispatching text, structured, and current-image structured calls to Ollama when `LOCAL_LLM_PROVIDER=ollama`.
- `gemma4:e2b` is installed locally in Ollama. Validation showed `ollama list` includes:
  - `gemma4:latest`
  - `gemma4:e2b`
- `gemma4:e2b` can answer text prompts through Ollama in the `blue-dream-sonic` conda environment.
- Ollama calls use `think=false` and structured calls use `format=json`.
- Current room snapshot object-presence checks now use Gemma/Ollama multimodal input instead of Nova vision.
- Object highlighting/localization remains Gemini spatial, not Gemma, because Gemma can detect object presence but is not reliable enough for precise boxes.
- Structured output parsing now strips JSON fences, extracts JSON from noisy content, validates with Pydantic, and retries once with stricter JSON instructions.
- Strands/Ollama was not used for Phase 1 because direct Ollama HTTP was already working and avoided new dependency risk.

### What We Will Do
- Added a local Gemma runtime for `gemma4:e2b`.
- Chosen implementation path:
  - direct Ollama HTTP client for `/api/chat`
- Routed text reasoning through Gemma for:
  - query routing
  - general responses
  - semantic evidence judging
  - answer synthesis
- Routed current room snapshot object-presence checks through Gemma vision via Ollama image input.
- Preserved Gemini spatial localization for bounding-box highlighting after Gemma confirms an object is visible.
- Fixed time-query routing so activity-history questions such as "What was I doing today?" route to the time agent instead of semantic retrieval.
- Fixed natural date parsing so prompts such as "April 18 2026" work in addition to ISO dates like `2026-04-18`.
- Preserved the existing `/query` API contract and frontend assumptions.
- Added robust output handling:
  - strip or ignore thinking traces
  - extract JSON from noisy responses
  - retry once with a stricter JSON-only prompt when structured parsing fails
  - return useful errors without crashing the API
- Kept Bedrock/Nova modules in the repo for embeddings and voice paths.

### Moving Forward
- Gemma is now the active text brain of the app.
- Gemini remains the active provider for full-video understanding and precise image localization/highlighting.
- Nova still exists in code for embeddings and voice. `/query` routing, synthesis, and current snapshot object checks no longer require Nova.
- Semantic retrieval still depends on Nova embeddings until Phase 2; if embeddings fail, `/query` returns a graceful insufficient-evidence response instead of crashing.

### Validation
- Verified `ollama list` includes `gemma4:e2b`.
- Ran direct local Gemma/Ollama smoke tests in `blue-dream-sonic` for:
  - text generation
  - structured output
  - fenced JSON extraction
  - multimodal structured object-presence checking against a stored image
- Ran syntax sanity checks for touched Python files in `blue-dream-sonic`.
- Tested `/query` in-process through the FastAPI app for:
  - one object query
  - one time query
  - one semantic query
  - one general query
- Confirmed all smoke responses returned HTTP 200 and matched `JeevesResponse`.
- Confirmed an in-process `/query` object smoke returned HTTP 200 and matched `JeevesResponse`.
- Confirmed direct single-image object test can use Gemma to detect black headphones in an older screenshot while bypassing stale Mongo latest-room state.
- Confirmed Gemini spatial test output is now observable through `gemini_spatial_result`, including raw text and errors when a highlighted image is not produced.
- Confirmed `/query` time question "What was I doing on April 18 2026?" returns a timeline from 10 stored Mongo events.
- Observed expected Phase 1 limitation: semantic retrieval still uses Nova embeddings and can fall back when Bedrock access is unavailable.

## Phase 2: Local Semantic Retrieval
**Status:** Validated

### Current Situation
- ChromaDB semantic search is implemented.
- MongoDB remains the source of truth for memory events.
- Semantic embeddings now use local Ollama `nomic-embed-text` by default.
- The active semantic collection is 768-dimensional and persisted under `Storage/chroma`.
- The production `memory_events` Chroma collection was reset and rebuilt from 30 MongoDB memory events.
- Raw legacy Mongo docs may still lack stored `semantic_text`, so rebuilds rely on `MemoryEvent` read-time normalization.
- Nova embedding code remains available only behind explicit `EMBEDDING_PROVIDER=bedrock`.
- Local testing showed `gemma4:e2b` does not support Ollama `/api/embed`, even though the model metadata reports an embedding length.
- Therefore Gemma 4 E2B should not be treated as the embedding backend.

### What We Will Do
- Added a dedicated local embedding backend through Ollama.
- Selected `nomic-embed-text` as the Phase 2 local embedding model.
- Added configurable settings:
  - `EMBEDDING_PROVIDER`
  - `LOCAL_EMBEDDING_MODEL`
  - `CHROMA_EMBEDDING_DIMENSION`
  - `CHROMA_PERSIST_DIR`
  - `CHROMA_COLLECTION_NAME`
- Reset/rebuild logic now detects persisted Chroma dimension/provider/model mismatches.
- Chroma stores only:
  - vector
  - event ID
  - lightweight metadata
- Keep MongoDB as the only full event store.

### Moving Forward
- Semantic recall now works without Nova embeddings.
- This makes the main recall path much easier to explain as local-first for the hackathon.
- Phase 3 is now the next planned implementation target.

### Validation
- Verified `ollama list` includes `nomic-embed-text:latest`.
- Verified direct Ollama `/api/embed` returns 768-dimensional vectors for `nomic-embed-text`.
- Ran `conda run -n blue-dream-sonic python -m compileall -q Blue_dream_agents`.
- Ran local embedding smoke test: provider `ollama`, model `nomic-embed-text`, dimension `768`.
- Ran vector-store smoke test against an in-memory Chroma collection, not production `memory_events`.
- Rebuilt `Storage/chroma` / `memory_events` from MongoDB; indexed count is 30 and collection metadata is provider `ollama`, model `nomic-embed-text`, dimension `768`.
- Tested semantic recall for music, bottle, and headphones queries; all returned matches and grounded answers.
- Confirmed sampled Chroma event IDs map back to Mongo `events` records.
- Confirmed `/query` route smokes for semantic, time, object, and general queries preserve the response model.

## Phase 2.5: Conversation Session Memory
**Status:** Validated

### Current Situation
- The patient web chat now supports optional short-term session memory for follow-up questions.
- `POST /query` still accepts the original `{ "query": "..." }` body for standalone clients.
- When the UI supplies `session_id`, the backend keeps recent turns in process memory and passes compact context into Jeeves.
- Conversation context is used to rewrite follow-up messages into standalone queries before routing and for general-chat responses only.
- The UI has a New Chat action that resets the backend session context and starts a fresh browser session ID.

### What We Did
- Added `Blue_dream_agents/conversation_memory.py` as a process-local store with recent-turn limits and inactive-session expiry.
- Extended `Blue_dream_agents/api.py` with optional `session_id` handling and `POST /conversation/reset`.
- Updated `Blue_dream_agents/jeeves.py` so object, time, and semantic tools receive a standalone resolved query while the response schema remains unchanged.
- Updated the static UI to generate a session ID, send it with `/query`, and expose New Chat.
- Kept MongoDB memory events and ChromaDB semantic indexing untouched.

### Moving Forward
- Phase 3 remains the next planned implementation target.
- Future mobile chat can reuse the optional `session_id` contract for per-session context.

### Validation
- Ran `python -m compileall -q Blue_dream_agents`.
- Ran a FastAPI `TestClient` smoke with mocked assistant calls for:
  - legacy `{ "query": "..." }` requests
  - `{ "query": "...", "session_id": "..." }` requests
  - context accumulation across turns
  - `POST /conversation/reset`
  - unchanged `JeevesResponse` keys
- Ran a Jeeves resolver smoke with mocked LLM/router calls confirming a follow-up query is rewritten and routed with conversation context.

## Phase 2.6: Memory Stack Audit Remediation
**Status:** Validated

### Current Situation
- The memory stack now has first-pass hardening for schema safety, ingestion reliability, vector-index maintenance, and prompt budgets.
- MongoDB remains the durable event store, and Chroma remains rebuildable semantic index state.
- Conversation memory remains process-local only and is not stored as patient evidence.

### What We Did
- Added MongoDB index setup for `timestamp`, `room_number + timestamp`, `event_id`, and `video_path`, called from API startup and the consolidator path.
- Fixed Gemini video result defaults so `room_objects` defaults to an empty list instead of a string.
- Updated the consolidator to use the shared MongoDB client, skip duplicate inserts by `video_path`, persist partial video/audio results, and still attempt semantic indexing after Mongo writes.
- Added prompt-budget compaction for high-volume time, object, and semantic evidence prompts.
- Cleaned `semantic_text` generation so empty fields no longer embed `"None"` sentinel text.
- Hardened Chroma reset/stale-vector cleanup and invalid `event_id` serialization behavior.
- Tightened conversation memory so object/time/semantic tools use the resolved standalone query without also receiving full chat history.

### Moving Forward
- Phase 3 remains the next planned implementation target.
- Future durability work can add a persistent dead-letter queue for failed video tasks and stronger content-hash idempotency.

### Validation
- Ran bytecode-free syntax compile smoke for touched Python files.
- Ran unit-style smokes for:
  - `video_results` defaults
  - valid and invalid `memory_event_to_mongo` event IDs
  - empty-field semantic text
  - prompt-budget compaction
  - narrower time-reference detection
- Ran FastAPI `TestClient` smoke for legacy `/query`, session `/query`, `/conversation/reset`, and unchanged response keys.
- Ran consolidator smoke confirming an audio failure still persists video results and duplicate `video_path` does not create a second insert.
- Ran local MongoDB index smoke and confirmed the expected indexes exist.
- Ran mocked retrieval-routing smoke for object, time, and semantic branches.

## Phase 3: Gemma Safety Agent
**Status:** In Progress

### Current Situation
- `Capture/camera_feed.py` starts recording when a person is detected.
- When the person exits the room, recording stops after a short detection buffer.
- The recorded video is queued through `Capture/video_processing_queue.py`.
- `Blue_dream_agents/consolidator.py` calls `Blue_dream_agents/video_agent.py`.
- `video_agent.py` asks Gemini for:
  - `video_description`
  - `room_objects`
- The planned implementation extends Gemini output with factual safety observations:
  - `danger_candidate`
  - `scene_end_state`
  - `observed_hazards`
  - `uncertainties`
- A new Gemma safety judge will own the warning decision and patient-facing explanation.
- Safety decisions will be persisted with the memory event.
- Actionable patient alerts will be stored in `safety_alerts`.
- The current model does not use a deterministic stove timer, person count policy, or external gas sensor.
- The first safety feature is intended to be visual and event-based.

### What We Will Do
- Keep Gemini as a full-video perception tool for the reliable path.
- Extend the video analysis output with factual safety fields only; Gemini must not decide whether to alert.
- Retry transient Gemini video-analysis failures such as 503 high-demand responses before storing a partial event.
- Add `Blue_dream_agents/safety_agent.py` as the Gemma safety judge.
- The safety judge reads:
  - Gemini factual video output
  - room metadata
  - timestamp
  - final screenshot path, when available
- The safety judge returns:
  - `warning_needed`
  - `severity`
  - `hazard_type`
  - `confidence`
  - `patient_message`
  - `detailed_explanation`
  - `recommended_action`
  - `caretaker_recommended`
- Initial safety scenario:
  - patient leaves a kitchen while a potentially dangerous cooking or stove/gas situation remains active.
- The safety judge should use conservative rules:
  - alert only when the observation clearly supports a risk
  - record uncertainty when the scene is ambiguous
  - avoid inventing hazards not present in the description
- Persist safety decisions with the event.
- If `warning_needed=true` and severity meets `SAFETY_ALERT_MIN_SEVERITY`, create a `safety_alerts` record.
- Safety assessment and alert creation failures must not block memory event insertion or Chroma indexing.

### Moving Forward
- After Phase 3, the project has an autonomous safety decision path where Gemma, not Gemini, owns the warning decision.
- This is the key hackathon story: Gemma is the local safety reasoning agent.
- The React Native app can build against the alert API contract before real FCM delivery is fully configured.

### Validation
- Test with at least one normal safe scene.
- Test with at least one kitchen or stove-like hazard scene.
- Test with one ambiguous scene where the system should store uncertainty rather than alert.
- Confirm MongoDB writes still include the canonical memory event fields.
- Confirm safety decision failures do not block memory event insertion.
- Confirm `/query` and `/conversation/reset` remain unchanged.

## Phase 4: Alert Delivery
**Status:** In Progress

### Current Situation
- Fall alerts are currently hardcoded inside `Capture/camera_feed.py`.
- The hardcoded fall alert sends email through Gmail.
- A generic alert service is being introduced for patient-actionable safety alerts.
- A fallen patient should not primarily receive a notification saying they fell.
- Patient notifications are appropriate only for actionable prompts, such as:
  - return to the kitchen
  - confirm they are okay after a geofence exit
  - follow guidance home

### What We Will Do
- Add `Blue_dream_agents/alert_service.py` as the generic alert service interface.
- Move hardcoded fall email behavior behind that alert service.
- Define alert recipient policy:
  - fall detected: notify caretaker or emergency contact, not the fallen patient
  - unattended kitchen risk: notify patient first if the message is actionable
  - high-severity kitchen risk: notify patient and caretaker
  - geofence exit: notify patient first, then caretaker if no safe response
  - low-confidence hazard: store only
- Use Firebase Cloud Messaging HTTP v1 as the planned patient push backend.
- Keep FCM optional for local development: if credentials are absent, alert records are stored with `delivery_status=not_configured` or `no_devices`.
- Store alert records with:
  - `alert_id`
  - alert type
  - severity
  - target recipient role
  - message
  - linked event ID
  - detail text for the mobile alert page
  - best-effort highlighted hazard image path, falling back to the original screenshot
  - `deep_link`, for example `memoria://alerts/{alert_id}`
  - delivery status
- Add mobile-compatible endpoints:
  - `POST /devices/register`
  - `GET /alerts/patient?status=open`
  - `GET /alerts/{alert_id}`
  - `POST /alerts/{alert_id}/ack`

### Moving Forward
- After Phase 4, safety decisions can turn into real notifications through a clean policy layer.
- This also prepares the mobile app to receive patient-facing safety prompts later.

### Validation
- Trigger a fall alert path and confirm it targets caretaker/emergency contact.
- Trigger an unattended kitchen warning and confirm it targets the patient when actionable.
- Confirm hardcoded recipient logic is removed or isolated behind config.
- Confirm alert records are stored or logged for later dashboard/mobile use.
- Confirm endpoints return JSON without exposing MongoDB `ObjectId` values.

## Phase 5: Mobile Patient App
**Status:** Planned

### Current Situation
- `Mobile/` is effectively empty in the current checkout, despite earlier roadmap wording about a Kotlin Compose skeleton.
- The main patient surface is still the FastAPI-served web UI.
- The mobile app does not yet provide chat, alert responses, geofence behavior, or Maps navigation.

### What We Will Do
- Build a text-first Expo React Native Android patient companion.
- Add backend configuration for local development API URL.
- Add patient chat against `POST /query`.
- Mirror the current `UI/` chat behavior:
  - stable per-session `session_id`
  - New Chat action through `POST /conversation/reset`
  - render `text`
  - render optional `image_path` for object localization
  - rewrite Windows/local `/Storage/` and `/Capture/` image paths to backend `/storage/` and `/capture/` URLs
- Add a basic alerts view for patient-actionable alerts.
- Add push notification registration against `POST /devices/register`.
- Open alert details from notification deep links such as `memoria://alerts/{alert_id}`.
- Add simple patient response actions:
  - `I'm OK`
  - `Guide me home`
- Use Android/Google Maps intents to launch navigation home.
- Keep the app simple for hackathon reliability.
- Defer:
  - voice input/output
  - multimodal mobile input/output
  - Uber booking
  - autonomous third-party app control
  - full on-device memory retrieval

### Moving Forward
- After Phase 5, the patient can use the mobile app for core text recall and basic safety interactions.
- This becomes the preferred patient-facing demo surface if stable.

### Validation
- Build the Android app.
- Confirm text chat can call the backend `/query`.
- Confirm object localization images render from `/storage` or `/capture` URLs.
- Confirm a patient-action alert can be displayed.
- Confirm FCM registration can call `/devices/register`.
- Confirm a notification tap opens the alert detail screen.
- Confirm `Guide me home` launches Google Maps navigation with configured home coordinates.

## Phase 6: Caretaker Dashboard
**Status:** Planned

### Current Situation
- There is no caretaker dashboard.
- The requested v1 caretaker scope is intentionally small.
- The first caretaker capability should be geofence management, not a broad analytics product.

### What We Will Do
- Add a minimal caretaker dashboard.
- Include:
  - view current geofence settings
  - update home latitude/longitude/radius
  - view recent safety alerts
- Geofence-compatible backend endpoints are planned as:
  - `GET /geofence/current`
  - `PUT /geofence/current`
  - `POST /geofence/events`
- Hackathon geofence behavior:
  - backend stores one default home center and radius
  - mobile checks location locally in the background
  - mobile posts an exit event when outside the radius
  - mobile opens Google Maps to the configured home coordinates when the patient taps Guide me home
- Keep authentication simple for demo unless the project is being prepared for real deployment.
- Avoid live video, rich analytics, and complex patient monitoring in v1.

### Moving Forward
- After Phase 6, the project can demonstrate a simple caregiver control surface.
- This supports the mobile geofence story without overbuilding.

### Validation
- Confirm caretaker can view geofence settings.
- Confirm caretaker can update geofence settings.
- Confirm recent alert records are visible.
- Confirm patient query flow still works.

## Phase 7: Demo and Submission Package
**Status:** Planned

### Current Situation
- Existing docs and article materials are Nova-oriented.
- The new hackathon story needs to clearly present Gemma as the reasoning and safety layer.
- The project still uses external APIs in places, so the submission must be honest about the architecture.

### What We Will Do
- Update `README.md`, `AGENTS.md`, and demo materials after implemented phases are validated.
- Prepare a concise demo script showing:
  - patient memory or object recall
  - safety event from room monitoring
  - Gemma safety decision
  - alert delivery to the right recipient
  - mobile or caretaker interaction if implemented
- Clearly document:
  - what runs locally through Gemma/Ollama
  - what uses Gemini as perception tooling
  - what remains legacy or future work
- Emphasize:
  - dementia support
  - caregiver trust
  - grounded memory evidence
  - local-first reasoning
  - patient safety

### Moving Forward
- After Phase 7, the project should be ready for a clean hackathon submission narrative and demo.

### Validation
- Run through the complete demo once from a clean start.
- Confirm setup instructions match the actual runtime.
- Confirm the README does not overclaim local-only behavior.
- Confirm `AGENTS.md` matches the actual completed architecture.

## Phase 8: Local Gemma Vision Prototype
**Status:** Planned

### Current Situation
- Local testing showed `gemma4:e2b` can process a still image through Ollama image input.
- Ollama does not appear to provide a direct MP4 video ingestion path for this installed model.
- Gemini full-video analysis remains the reliable path.
- This phase is intentionally last because it is exploratory and should not destabilize the main demo.

### What We Will Do
- Add an OpenCV frame sampler for recorded video clips.
- Sample a small number of frames from the beginning, middle, and end of a clip.
- Send sampled frames to local `gemma4:e2b` through Ollama image input.
- Ask Gemma for structured visual safety observations.
- Compare the local frame-based assessment against:
  - Gemini full-video description
  - Gemma safety judge output
- Use this as an edge-deployment prototype, not the core reliable path unless it validates well.

### Moving Forward
- After Phase 8, the project may have a stronger local/edge Gemma story.
- If the prototype is unreliable, keep it as a documented experiment rather than part of the main demo.

### Validation
- Test local frame sampling on at least one stored video.
- Confirm Gemma can receive and reason over sampled frames.
- Confirm output is structured enough for the safety judge.
- Compare results against the reliable Gemini-video path.

## Planned Configuration
- `LOCAL_LLM_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://localhost:11434`
- `GEMMA_TEXT_MODEL=gemma4:e2b`
- `GEMMA_VISION_MODEL=gemma4:e2b`
- `EMBEDDING_PROVIDER=ollama`
- `LOCAL_EMBEDDING_MODEL=nomic-embed-text`
- `CHROMA_EMBEDDING_DIMENSION=768`
- `GEMINI_VIDEO_MODEL=gemini-3-flash-preview`
- `GEMINI_VIDEO_FALLBACK_MODELS=gemini-2.5-flash`
- `GEMINI_VIDEO_MAX_RETRIES=3`
- `GEMINI_VIDEO_RETRY_BASE_SECONDS=4`
- `SAFETY_AGENT_ENABLED=true`
- `SAFETY_ALERT_MIN_SEVERITY=medium`
- `FIREBASE_PROJECT_ID=<firebase-project-id>`
- `FIREBASE_CREDENTIALS_PATH=<gitignored-service-account-json-path>`
- `FIREBASE_ANDROID_PACKAGE=<android-package-name>`
- `PATIENT_HOME_LAT=<latitude>`
- `PATIENT_HOME_LNG=<longitude>`
- `PATIENT_GEOFENCE_RADIUS_METERS=<radius>`

## Notes For Fresh Context Windows
- Start with the first phase not marked `Validated` or `Committed`.
- Phase 3 is the next planned phase after validated local semantic retrieval.
- Do not start with mobile, dashboard, alert delivery, or local Gemma vision before the Gemma safety agent is stable.
- Keep Gemini for full-video perception until local Gemma frame sampling is proven.
- Keep Gemini for spatial localization/highlighting; Gemma is currently used for object-presence checks, not precise object boxes.
- Fall alerts go to caretaker or emergency contact.
- Patient alerts should only be sent for actionable situations where the patient can safely respond.
- Preserve existing API/UI contracts unless an explicit migration phase says otherwise.
