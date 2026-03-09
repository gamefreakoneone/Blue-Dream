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
- The patient web app remains the primary surface.
- MongoDB remains the source of truth for memory events.
- ChromaDB is planned as the vector index for semantic memory search.
- Amazon Nova is the primary planned model family for:
  - routing
  - semantic embeddings
  - semantic synthesis
  - voice
- Gemini remains the planned exception for:
  - long-form video understanding
  - image bounding/localization

## Platform Assumptions
- Primary development environment: Windows + PowerShell.
- Python project with local execution style (no formal packaging config in repo root).
- MongoDB is expected to run locally unless `MONGODB_URI` overrides it.

## Canonical Runtime Commands
- Start backend API + UI static hosting:
```powershell
uvicorn Blue_dream_agents.api:app --reload
```
- Start capture pipeline:
```powershell
python Capture/camera_feed.py
```
- Access UI:
  - `http://localhost:8000`

## Critical Interfaces (Do Not Break)

### 1) API Query Contract
- Endpoint: `POST /query`
- Request body:
```json
{ "query": "Where are my keys?" }
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
- Legacy Mongo docs are still supported through read-time normalization:
  - `event_id` falls back to `_id`
  - `room_name` falls back to the shared room map
  - `semantic_text` is built from the event fields if absent
- Active retrieval paths in `time_agent.py` and `object_detector.py` now normalize Mongo docs through `MemoryEvent` before reasoning over them.

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
  - -> MongoDB `dementia_assistance.events`
- Assistant request pipeline:
  - `Blue_dream_agents/api.py` (`POST /query`)
  - -> `Blue_dream_agents/jeeves.py` (Strands orchestrator on native Bedrock)
  - -> `Blue_dream_agents/time_agent.py` and `Blue_dream_agents/object_detector.py`
  - -> `Blue_dream_agents/memory_schema.py` for canonical event reads
  - -> `Blue_dream_agents/llm/settings.py`
  - -> `Blue_dream_agents/llm/model_registry.py`
  - -> `Blue_dream_agents/llm/bedrock_client.py`
  - -> `Blue_dream_agents/llm/strands_runtime.py`
- Frontend:
  - `UI/index.html`, `UI/script.js`, `UI/styles.css`
  - `UI/script.js` posts to `/query` and renders optional images.

## Source-of-Truth Files vs Legacy/Archive

### Active Source-of-Truth (default edit targets)
- `Blue_dream_agents/api.py`
- `Blue_dream_agents/jeeves.py`
- `Blue_dream_agents/time_agent.py`
- `Blue_dream_agents/object_detector.py`
- `Blue_dream_agents/memory_schema.py`
- `Blue_dream_agents/llm/settings.py`
- `Blue_dream_agents/llm/model_registry.py`
- `Blue_dream_agents/llm/bedrock_client.py`
- `Blue_dream_agents/llm/strands_runtime.py`
- `Blue_dream_agents/consolidator.py`
- `Blue_dream_agents/video_agent.py`
- `Blue_dream_agents/audio_transcribe.py`
- `Blue_dream_agents/timezone_utils.py`
- `Capture/camera_feed.py`
- `Capture/video_processing_queue.py`
- `Capture/audio_capture.py`
- `UI/index.html`
- `UI/script.js`
- `UI/styles.css`

### Planning Source-of-Truth
- `PLANS.md` is the source of truth for overhaul sequencing and feature status.
- Code files remain the source of truth for current runtime behavior.

### Legacy / Non-Authoritative (avoid unless task explicitly requires)
- `Blue_dream_agents/time-agent copy.py`
- `Blue_dream_agents/object-detector(archive).py`
- Training/experimental artifacts in `Capture/trained-weights/training_code.py`
- Notebook and demo/proof materials unless task is documentation/demo related.

## Environment + Secrets
- Required keys in `.env` for core behavior:
  - `AWS_BEARER_TOKEN_BEDROCK` or standard AWS credentials/profile
  - `GEMINI_API_KEY`
  - Optional: `MONGODB_URI`
- Optional Nova overrides:
  - `NOVA_ROUTER_MODEL`
  - `NOVA_SYNTHESIS_MODEL`
  - `NOVA_VISION_MODEL`
  - `NOVA_VISION_FALLBACK_MODEL`
  - `BEDROCK_AWS_REGION`
  - `BEDROCK_API_KEY_REGION`
- Current Bedrock-native defaults/expectations:
  - standard AWS credentials path prefers `BEDROCK_AWS_REGION=us-east-2`
  - API-key auth path falls back to a Bedrock-supported API-key region if needed
  - Nova 2 Lite should be referenced through the inference-profile style model ID, for example `us.amazon.nova-2-lite-v1:0`
- Gmail integration expects:
  - `Blue_dream_agents/Tools/credentials.json`
  - Generated token: `Blue_dream_agents/Tools/token.pickle`
- Never commit secrets, tokens, credential files, or local auth artifacts.

## Known Quirks Agents Must Respect
- `README.md` references `GOOGLE_API_KEY`, while code uses `GEMINI_API_KEY`.
- `time_agent.py` now routes through structured Strands prompts rather than an exported SDK agent object.
- `semantic_text` is now the canonical event-text representation; Feature 3 should embed it rather than redefine it.
- `Capture/camera_feed.py` currently uses hardcoded camera indices `[1, 2]`.
- `Capture/camera_feed.py` has a hardcoded fall-alert recipient email.
- `Blue_dream_agents/sam3_api.py` contains local-machine-specific SAM3 root/CWD behavior.
- Bedrock-native access is now the active Nova path.
- Nova 2 Lite requests may fail with the bare model ID `amazon.nova-2-lite-v1:0`; the working Bedrock path is the inference-profile style ID such as `us.amazon.nova-2-lite-v1:0`.
- API-key auth is region-limited, so the runtime falls back to a supported API-key region when standard AWS credentials are not present.
- Some imports used by code are not represented in `requirements.txt` (for example `chromadb`, Gmail auth client libs).
- Repository includes real `Storage/` media artifacts; treat them as runtime data, not source code.

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
- Feature 1: Nova provider integration and routing refactor
- Feature 2: canonical memory event schema
- Feature 3: semantic search foundation
- Feature 4: semantic-to-time fallback reasoning
- Feature 5: Gemini spatial localization replacement
- Feature 6: voice support with Nova
- Feature 7: conversation memory
- Feature 8: demo and submission readiness

## Validation Checklist for Future Agent Work
- For touched Python files:
  - run a minimal syntax/type sanity pass appropriate to the change.
- For API-touching changes:
  - run backend and smoke-test `POST /query`.
- For capture-pipeline changes:
  - verify queue handoff (`camera_feed` -> `VideoProcessingQueue` -> `consolidator_agent`) remains intact.
  - verify Mongo insert payload still contains expected event fields.
- For UI changes:
  - verify chat rendering still handles `text` + optional `image_path`.
  - verify `/storage` and `/capture` path rewriting still works.

## Documentation Update Test Cases (This Change)
- Confirm commands in this doc match executable entrypoints in repository files.
- Confirm listed API and event-schema fields match current code paths.
- Confirm quirks listed here are present in current implementation.
- Confirm this change modifies documentation only and does not alter runtime behavior.

## Baseline Note
- This AGENTS file intentionally documents the present implementation and quirks.
- Feature 2 canonical memory-event schema is now part of the current implementation baseline.
- Expect this file to be revised as the planned architecture overhaul proceeds.
