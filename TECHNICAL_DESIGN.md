# Project Memoria Technical Design

> **Reading this document.** This describes the *target* architecture for the rebuild. Anything attributed to a spec number (e.g. `Blue_dream_agents/llm/client.py`, `media_paths.py`, `tests/`, the memory-lifecycle collections) does not exist until that spec is completed — `docs/FEATURE_STATUS.md` is the authority on what is implemented today. The pre-rebuild baseline is described in `docs/archive/`.

## Architecture Summary

Memoria has five layers:

1. **Capture** (`Capture/`) records room events on the local machine: YOLO person/fall detection, per-camera video + audio recording, final-frame screenshots, a processing queue.
2. **Ingestion** (`Blue_dream_agents/consolidator.py`) turns a finished recording into a canonical `MemoryEvent`: video description + factual safety observations (vision model), audio transcript (ASR), importance score, safety judgment, MongoDB insert, semantic indexing.
3. **Memory stores**: MongoDB (`dementia_assistance`) is the single source of truth — `events`, `memory_summaries`, `conversation_sessions`, `profile_facts`, `reminders`, `safety_alerts`, `proactive_messages`. ChromaDB is a rebuildable semantic index only.
4. **Provider layer** (`Blue_dream_agents/llm/`) is one async client speaking the OpenAI chat-completions protocol to DashScope (Qwen), OpenAI, or local Ollama, selected by `LLM_PROVIDER`.
5. **Interaction** (`Blue_dream_agents/api.py` + `UI/`) serves the patient chat (text + voice + proactive turns), alerts, geofence, and static media; `Mobile/` is a prototype-stage Expo app kept for future work.

## Development Environment

- Windows 11 + PowerShell; Python via the `Project-Memoria` conda environment.
- MongoDB local (`mongodb://localhost:27017`) unless `MONGODB_URI` overrides.
- Default provider: `LLM_PROVIDER=qwen` (DashScope; key read from `DASHSCOPE_API_KEY` with `QWEN_APIKEY` fallback). OpenAI profile used only in spec 0012. Ollama is an optional local profile — not installed on the dev machine, never a prerequisite.
- Run backend: `uvicorn Blue_dream_agents.api:app --reload` (add `--host 0.0.0.0` for LAN).
- Run capture: `python Capture/camera_feed.py`.
- Tests: `python -m pytest tests/` (scaffolded in spec 0001).
- Dependencies are pinned in `requirements.txt`; when adding a dependency, pin it in the same change.

## Key Contracts

### `MemoryEvent` (MongoDB `events`)

Canonical model in `Blue_dream_agents/memory_schema.py`. Existing fields (`event_id`, `timestamp`, `room_number`, `room_name`, `video_description`, `room_objects`, `audio_transcript`, `screenshot_path`, `video_path`, `audio_path`, `semantic_text`, safety fields) plus lifecycle fields added by spec 0007: `importance` (0–1), `importance_reason`, `pinned`, `lifecycle_status` (`active|consolidated`), `consolidated_into`. Legacy documents are normalized at read time — never bulk-migrated.

### Media paths

- **Stored form** (MongoDB): relative POSIX path from the project root, e.g. `Storage/screenshots/room0_20260718_101500.jpg`.
- **API form** (all responses): URL path under a static mount, e.g. `/storage/screenshots/room0_20260718_101500.jpg`.
- **Filesystem form** (internal reads): absolute path resolved against `MEDIA_ROOT` (defaults to the project root).
- `Blue_dream_agents/media_paths.py` owns all three conversions plus `normalize_stored_path()` for legacy absolute Windows paths.

### `JeevesResponse` (`POST /query`)

```json
{
  "response_type": "search_result | activity | general",
  "text": "string",
  "image_path": "string | null",
  "data": "object | null"
}
```

`image_path` is always a URL path. `data.recall_debug` (spec 0007) lists the memories packed into the answer. Request body stays `{ "query": "...", "session_id": "optional" }`.

### New endpoints

| Endpoint | Shape | Spec |
|---|---|---|
| `GET /memory/profile` | list of profile facts | 0006 |
| `POST /memory/profile/{fact_id}/pin`, `.../archive` | `{ "ok": true }` | 0006 |
| `GET /reminders`, `POST /reminders` | reminder list / create | 0006 |
| `POST /reminders/{reminder_id}/done` | `{ "ok": true }` | 0006 |
| `POST /memory/consolidate` | consolidation run report | 0007 |
| `POST /memory/events/{event_id}/pin`, `.../unpin` | `{ "ok": true }` (pin re-activates + re-embeds) | 0007 |
| `GET /proactive/pending?session_id=` | pending agent-initiated messages | 0008 |
| `POST /proactive/{message_id}/ack` | `{ "ok": true }` | 0008 |
| `POST /voice/transcribe` | audio blob → `{ "text": ... }` | 0009 |
| `POST /voice/speak` | `{ "text": ... }` → audio bytes | 0009 |
| `GET /voice/capabilities` | `{ "transcribe": bool, "tts": bool }` | 0009 |
| `POST /ingest/event` | multipart event JSON + screenshot; `X-Ingest-Token` header | 0010 |
| `GET /memory/summaries?days=` | daily memory summaries (caregiver dashboard) | 0012 |
| `GET /alerts/recent?limit=` | recent alerts, all roles (caregiver dashboard) | 0012 |

Existing contracts preserved: `POST /conversation/reset`, alert endpoints, geofence endpoints, `/storage` + `/capture` static mounts.

## Provider Architecture

One client (`Blue_dream_agents/llm/client.py`, built on `openai.AsyncOpenAI`) serves every capability. `LLM_PROVIDER` selects the profile; per-capability env vars override individual pieces. Working configuration: dev and the Qwen demo run `qwen`; spec 0012 flips to `openai` for the Build Week submission; `ollama` is an optional local profile that is never required or validated in this rebuild.

| Capability | qwen (DashScope) | openai | ollama (optional local profile) |
|---|---|---|---|
| Text: routing/synthesis/judging | `qwen-plus` (routing/judging), `qwen-max` (synthesis — matches spec 0003 presets) | `gpt-5.6` | `gemma4:e2b` |
| Vision: presence checks | `qwen-vl-max` | `gpt-5.6` | `gemma4:e2b` |
| Spatial grounding (boxes) | `qwen-vl-max` (stretch) | Gemini fallback | Gemini fallback |
| Video understanding | `qwen-vl-max` frame sampling (stretch) | Gemini fallback | Gemini fallback |
| Embeddings | `text-embedding-v4` (1024d) | `text-embedding-3-small` (1536d) | `nomic-embed-text` (768d) |
| Speech-to-text | `qwen3-asr-flash` | `gpt-4o-transcribe` | — (browser fallback) |
| Text-to-speech | Qwen TTS (verify model in 0005 spike) | `gpt-4o-mini-tts` | — (browser fallback) |

Env surface: `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `VIDEO_PROVIDER=qwen|gemini`, `SPATIAL_PROVIDER=qwen|gemini`, `TRANSCRIBE_PROVIDER=qwen|openai`, `TTS_PROVIDER=qwen|openai|none`; `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`, `GEMINI_API_KEY`; per-task model overrides (`LLM_TEXT_MODEL`, `LLM_VISION_MODEL`, `LLM_EMBEDDING_MODEL`, `LLM_EMBEDDING_DIM`, ...).

Structured-output hardening (JSON fence stripping, embedded-JSON extraction, Pydantic validation, one strict retry) is provider-agnostic and applied on every structured call, with native JSON modes layered on top (`json_object` for DashScope/Ollama, `json_schema` strict structured outputs for GPT-5.6).

### Per-provider Chroma collections

Embedding models produce incompatible vector spaces (768 vs 1024 vs 1536 dims), so each provider/model pair gets its own collection: `memory_events__{provider}__{model_slug}__{dim}`. Switching providers creates a sibling collection and triggers a rebuild from MongoDB (seconds at current scale); it never destroys another provider's index. Collection metadata records provider/model/dim; there is no inspection of Chroma's internal SQLite files.

## Memory System

Retrieval flow:

> Question → Chroma (active provider's collection) returns top-K candidates → MongoDB fetches the full truth records → re-rank: `final_score = similarity × exp(-age_days / RECALL_HALF_LIFE_DAYS) × (1 + importance)`, pinned items guaranteed → greedy pack into `RECALL_TOKEN_BUDGET` → synthesis prompt = profile facts + packed evidence → answer + `recall_debug`.

- **Conversation memory** (`conversation_sessions`): persisted turns with automatic summarization beyond a turn limit; survives restarts; still never indexed in Chroma and never used as monitoring evidence.
- **Profile facts** (`profile_facts`): stable personal facts extracted after chat turns, LLM-deduplicated, small enough to always inject into prompts; pin/archive via API.
- **Reminders** (`reminders`): timed items created from chat or API, delivered by the proactive channel.
- **Lifecycle**: importance scored at ingest; a consolidation job groups old low-importance events by day + room into `memory_summaries`, embeds the summary, removes the originals from Chroma, and marks them `consolidated` in MongoDB. Nothing is ever deleted; the time agent reads MongoDB directly and is unaffected. Pinned items never consolidate.

## Proactive Channel

`proactive_messages` records are created by triggers: safety alert stored (actionable patient warning), geofence exit (check-in + Google Maps home link), first sighting of the day (morning report), reminder due. The web UI polls `GET /proactive/pending` every few seconds and renders messages as agent-initiated chat turns; acknowledgment marks them delivered. No push infrastructure.

## Critical Design Rules

- MongoDB is the only source of truth; Chroma must always be rebuildable from it.
- Memory is archived or consolidated, never erased.
- Patient-facing text never contains raw exception strings; failures log fully server-side and return a fixed reassuring message.
- Conversation memory is not monitoring evidence and is never embedded.
- `image_path` leaving the API is always a URL path.
- The `/query`, `/conversation/reset`, alert, and geofence contracts must not break; the web UI and mobile app both consume them.
- Capture stays functional standalone; cloud ingestion is opt-in via `INGEST_URL`.

## Intentional Design Decisions — Preserve During Rebuild

Behaviors that look like bugs but are deliberate; do not "fix" them without a spec saying so:

- **Capture debounces** (spec 0004): the 2s no-person buffer before stopping a recording tolerates YOLO false negatives and brief frame exits; the 3.5s fall-persistence window, 0.50 confidence threshold, and once-per-recording fall-alert guard prevent alert spam. Make them env-tunable with the same defaults; treat the values as tuned, not arbitrary.
- **End-of-event screenshot** (spec 0004): the saved screenshot deliberately captures the room *after* the person leaves — the end state is the best evidence for object-finding and unattended-hazard checks.
- **fps=20 and default-microphone audio** (spec 0004): accepted hardware/single-occupant tradeoffs (two-room home, one active camera at a time). Do not add per-camera microphone plumbing; an optional `device_index` passthrough is the ceiling.
- **Gemini video fallback chain** (`GEMINI_VIDEO_FALLBACK_MODELS` + retry env vars, spec 0003): a workaround for flaky preview models; preserve the fallback chain wherever Gemini remains the video/spatial fallback.
- **Conversation memory in MongoDB** (spec 0006): a conscious reversal of the archived pre-rebuild rule, required for cross-session persistence. The two original boundaries still hold: chat turns are never embedded in Chroma and never treated as monitoring evidence.

Two implementation cautions for cleanups that *are* wanted: alert/index initialization must run once per process (alerts are created from both the API server and the capture pipeline process — FastAPI lifespan alone does not cover capture), and both `uvicorn Blue_dream_agents.api:app` and `python Capture/camera_feed.py` invocations must keep working after any import-pattern cleanup.

## DashScope Assumptions To Verify (spec 0005 spike, before dependent code)

1. Correct base URL for the account region (`dashscope-intl.aliyuncs.com` vs `dashscope.aliyuncs.com`) and current model names.
2. `response_format: json_object` support for the chosen text model in compatible mode.
3. `text-embedding-v4` availability on the compatible-mode `/embeddings` endpoint, its `dimensions` parameter, and the per-request batch limit (chunk `embed_texts` accordingly).
4. Qwen-VL grounding output: bounding-box coordinate convention (absolute pixels vs 0–1000 normalized) and reliability through compatible mode.
5. Video-as-frames: whether compatible mode accepts a `video` content part with base64 frames; fallback is multiple `image_url` parts with a sequential-frames prompt.
6. ASR/TTS endpoint shapes: OpenAI-style `/audio/*` in compatible mode, or the native `dashscope` SDK (model names for `qwen3-asr-flash` and the current TTS model).

## Reference Documents

- `docs/FEATURE_STATUS.md` — the project ledger; check before starting work.
- `docs/specs/0001-...` through `docs/specs/0012-...` — per-feature requirements, design, tasks, status.
- `docs/DEPLOYMENT_ALIBABA.md` — cloud deployment walkthrough (stretch).
- `docs/SUBMISSIONS.md` — hackathon requirement checklists and video scripts.
- `docs/archive/` — pre-rebuild AGENTS/PLANS baselines (historical record of the earlier architecture).
