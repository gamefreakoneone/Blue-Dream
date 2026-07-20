# Project Memoria Technical Design

> **Reading this document.** This describes the *target* architecture for the rebuild. Anything attributed to a spec number (e.g. `Blue_dream_agents/llm/client.py`, `media_paths.py`, `tests/`, the memory-lifecycle collections) does not exist until that spec is completed — `docs/FEATURE_STATUS.md` is the authority on what is implemented today. The pre-rebuild baseline is described in `docs/archive/`.

## Architecture Summary

Memoria has five layers:

1. **Capture** (`Capture/`) records room events on the local machine: YOLO person/fall detection, per-camera video + audio recording, final-frame screenshots, a processing queue.
2. **Ingestion** (`Blue_dream_agents/consolidator.py`) turns a finished recording into a canonical `MemoryEvent`: video description + factual safety observations (vision model), audio transcript (ASR), importance score, safety judgment, MongoDB insert, semantic indexing.
3. **Memory stores**: MongoDB (`dementia_assistance`) is the single source of truth — `events`, `memory_summaries`, `conversation_sessions`, `profile_facts`, `reminders`, `safety_alerts`, `proactive_messages`, `push_subscriptions`. `memory_digests` is a date-keyed, rebuildable presentation cache derived from those authoritative records. ChromaDB is a rebuildable semantic index only.
4. **Provider layer** (`Blue_dream_agents/llm/`) is one async client speaking the OpenAI chat-completions protocol to DashScope (Qwen), OpenAI, or local Ollama, selected by `LLM_PROVIDER`.
5. **Interaction** (`Blue_dream_agents/api.py` + `UI/`) is a Vite + React installable patient PWA built to `UI/dist`. It serves chat, proactive turns, reminders, safety, memories, alerts, and static media; Web Push wakes the service worker when the app is closed. The former Expo `Mobile/` prototype was removed by spec 0013.

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

Canonical model in `Blue_dream_agents/memory_schema.py`. Existing fields (`event_id`, `timestamp`, `room_number`, `room_name`, `video_description`, `room_objects`, `audio_transcript`, `screenshot_path`, `video_path`, `audio_path`, `semantic_text`, safety fields) plus lifecycle fields added by spec 0007: `importance` (0–1), `importance_reason`, `pinned`, `lifecycle_status` (`active|consolidated`), `consolidated_into`; plus the optional `video_oss_key` added by spec 0005 (OSS object key of the uploaded video, absent on legacy documents). Legacy documents are normalized at read time — never bulk-migrated.

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
| `POST /reminders/{reminder_id}/archive` | `{ "ok": true }`; 404 when unknown/inactive | 0013a |
| `POST /memory/consolidate` | consolidation run report | 0007 |
| `POST /memory/events/{event_id}/pin`, `.../unpin` | `{ "ok": true }` (pin re-activates + re-embeds) | 0007 |
| `GET /proactive/pending?session_id=` | pending messages; additive `related_id` links safety messages to their alert | 0008, 0013a |
| `POST /proactive/{message_id}/ack` | `{ "ok": true }` | 0008 |
| `POST /voice/transcribe` | audio blob → `{ "text": ... }` | 0009 |
| `POST /voice/speak` | `{ "text": ... }` → audio bytes | 0009 |
| `GET /voice/capabilities` | `{ "transcribe": bool, "tts": bool }` | 0009 |
| `POST /ingest/event` | multipart event JSON + screenshot; `X-Ingest-Token` header | 0010 |
| `GET /push/vapid-public-key` | `{ "enabled": bool, "key": string }` | 0013 |
| `POST /push/subscribe`, `/push/unsubscribe`, `/push/test` | Web Push subscription lifecycle / test result | 0013 |
| `GET /memory/summaries?days=` | newest-first, JSON-safe daily memory summaries | 0013 (pulled forward from 0012) |
| `GET /memory/digest?days=&force=` | newest-first daily narratives from the rebuildable date-keyed cache | 0013a |
| `GET /alerts/recent?limit=` | recent alerts, all roles (caregiver dashboard) | 0012 |

Existing contracts preserved: `POST /query`, `POST /conversation/reset`, alert endpoints, geofence endpoints, `POST /devices/register`, `/storage` + `/capture` static mounts, and the byte-for-byte `GET /memory/summaries` response.

## Provider Architecture

One client (`Blue_dream_agents/llm/client.py`, built on `openai.AsyncOpenAI`) serves every capability. `LLM_PROVIDER` selects the profile; per-capability env vars override individual pieces. Working configuration: dev and the Qwen demo run `qwen`; spec 0012 flips to `openai` for the Build Week submission; `ollama` is an optional local profile that is never required or validated in this rebuild.

| Capability | qwen (DashScope) | openai | ollama (optional local profile) |
|---|---|---|---|
| Text: routing/synthesis/judging | `qwen3.7-plus` (thinking disabled on latency-sensitive routing/judging calls; spike-confirmed in 0005, superseding the spec 0003 `qwen-plus`/`qwen-max` presets) | `gpt-5.6` | `gemma4:e2b` |
| Vision: presence checks | `qwen3-vl-flash` | `gpt-5.6` | `gemma4:e2b` |
| Spatial grounding (boxes) | `qwen3-vl-plus` (high-precision localization; Gemini fallback on failure) | Gemini fallback | Gemini fallback |
| Video understanding | `qwen3-vl-flash` via presigned OSS video URL (primary; 2 GB / 1 h URL ceilings); full-video Gemini fallback | Gemini fallback | Gemini fallback |
| Embeddings | `text-embedding-v4` (1024d) | `text-embedding-3-small` (1536d) | `nomic-embed-text` (768d) |
| Speech-to-text | `qwen3-asr-flash` | `gpt-4o-transcribe` | — (browser fallback) |
| Text-to-speech | `qwen3-tts-flash` (spike-confirmed in 0005) | `gpt-4o-mini-tts` | — (browser fallback) |

Env surface: `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `VIDEO_PROVIDER=qwen|gemini`, `SPATIAL_PROVIDER=qwen|gemini`, `TRANSCRIBE_PROVIDER=qwen|openai`, `TTS_PROVIDER=qwen|openai|none`; `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`, `GEMINI_API_KEY`; OSS video bridge (`OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, `OSS_BUCKET`, `OSS_ENDPOINT`, `OSS_PRESIGN_TTL_SECONDS`); Web Push and reminder sweep (`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`, `REMINDER_SWEEP_SECONDS`); per-task model overrides (`LLM_TEXT_MODEL`, `LLM_SYNTHESIS_MODEL`, `LLM_VISION_MODEL`, `LLM_SPATIAL_MODEL`, `LLM_VIDEO_MODEL`, `LLM_EMBEDDING_MODEL`, `LLM_EMBEDDING_DIM`, `LLM_TRANSCRIBE_MODEL`, `LLM_TTS_MODEL`, `GEMINI_SPATIAL_MODEL`); request/runtime controls (`EMBED_BATCH_SIZE`, `LLM_DEFAULT_TEMPERATURE`, `LLM_DEFAULT_MAX_TOKENS`, `LLM_REQUEST_TIMEOUT_SECONDS`).

Structured-output hardening (JSON fence stripping, embedded-JSON extraction, Pydantic validation, one strict retry) is provider-agnostic and applied on every structured call, with native JSON modes layered on top (`json_object` for DashScope/Ollama, `json_schema` strict structured outputs for GPT-5.6).

### OSS video bridge (spec 0005)

Inline (base64) video to DashScope is capped at 10 MB after encoding; URL-fed video supports far larger files (2 GB / up to 1 h for Qwen3-VL). Recorded event videos are therefore uploaded to a private Alibaba OSS bucket (`memoria`, Singapore/ap-southeast-1 — same region as the DashScope intl endpoint) and consumed by `qwen3-vl-flash` as a `video_url` content part via a presigned URL. Rules:

- `Blue_dream_agents/oss_media.py` owns the bridge: `upload_video(fs_path) -> object_key` and `presigned_url(object_key, ttl) -> str` (SDK: `oss2`, pinned when spec 0005 lands). The object key mirrors the stored relative POSIX path (e.g. `Storage/video_recordings/camera_0/camera_0_20260718_101500.mp4`), so keys are derivable from `video_path`.
- Upload happens at ingestion: the consolidator uploads the finished video immediately before the video-understanding call and stores the object key on the event (`video_oss_key`). The local file remains the source of truth; OSS is a transfer bridge for model access, never a media store for the UI (`/storage` static serving is unchanged).
- Capture MP4s are intentionally silent. The paired microphone file is transcribed independently, and the consolidator combines its transcript with the full-video visual description before Mongo/Chroma persistence.
- The bucket stays private; access is only via presigned URLs with a bounded TTL (`OSS_PRESIGN_TTL_SECONDS`, default 3600).
- Fallback ladder for `VIDEO_PROVIDER=qwen`: OSS-URL Qwen video understanding → existing full-video Gemini analysis → partial event. Frame sampling is intentionally excluded so long recordings retain full temporal context. OSS being unreachable degrades video understanding; it never blocks event ingestion.

### Per-provider Chroma collections

Embedding models produce incompatible vector spaces (768 vs 1024 vs 1536 dims), so each provider/model pair gets its own collection: `memory_events__{provider}__{model_slug}__{dim}`. Switching providers creates a sibling collection and triggers a rebuild from MongoDB (seconds at current scale); it never destroys another provider's index. Collection metadata records provider/model/dim; there is no inspection of Chroma's internal SQLite files.

## Memory System

Retrieval flow:

> Question → Chroma (active provider's collection) returns top-K candidates → MongoDB fetches the full truth records → re-rank: `final_score = similarity × exp(-age_days / RECALL_HALF_LIFE_DAYS) × (1 + importance)`, pinned items guaranteed → greedy pack into `RECALL_TOKEN_BUDGET` → synthesis prompt = profile facts + packed evidence → answer + `recall_debug`.

- **Conversation memory** (`conversation_sessions`): persisted turns with automatic summarization beyond a turn limit; survives restarts; still never indexed in Chroma and never used as monitoring evidence.
- **Profile facts** (`profile_facts`): stable personal facts extracted after chat turns, LLM-deduplicated, small enough to always inject into prompts; pin/archive via API.
- **Reminders** (`reminders`): created from chat or API in two kinds discriminated by `trigger_type` — `time` (wall-clock `due_at`, optional daily recurrence) and `event` (fires when a matching camera event is ingested: room + local-time window + natural-language behavior condition + optional `valid_date`). The Jeeves router has an additive `reminder` intent: it extracts and creates the reminder synchronously, then returns a deterministic local-time confirmation without a second LLM call. Chat-created reminders carry `origin_context` (session id + original phrasing) in Mongo as an audit trail. An event reminder with no time constraint uses 00:00–23:59; only explicitly morning-ish wording narrows it to 06:00–11:00. Delivery is the proactive channel's job; `reminder_service` exposes `get_due_reminders(now)` and `get_matchable_event_reminders(now)` for it. Marking a daily time reminder done rolls `due_at` to its next occurrence and leaves it active in both patient and delivery modes; patient one-shot and event reminders archive, while delivery one-shots preserve their existing `done` transition.
- **Working memory**: the small always-injected context block — active profile facts plus active reminders — served by plain indexed MongoDB reads on every prompt. Deliberately *not* a file on disk (the API server and capture pipeline are separate processes, and MongoDB is the single source of truth) and *not* vector-backed (no embedding or Chroma lookup is involved; retrieval is a few milliseconds). This is the fast-recall tier for things the agent must never have to search for.
- **Lifecycle**: importance scored at ingest; a consolidation job groups old low-importance events by day + room into `memory_summaries`, embeds the summary, removes the originals from Chroma, and marks them `consolidated` in MongoDB. Nothing is ever deleted; the time agent reads MongoDB directly and is unaffected. Pinned items never consolidate.
- **Daily digests** (`memory_digests` cache): `DailyDigestService` builds a patient-safe narrative for each local day from that day's summaries plus active raw events, including raw-event-only days that are not yet consolidated. The cache is uniquely keyed by date and fingerprinted from the included source IDs; unchanged fingerprints make repeat reads zero-LLM, while `force=true` rebuilds. Per-day failures serve a stale cached digest when possible or omit only the failed day. The public response excludes Mongo `_id` and the internal fingerprint. Authoritative memories remain in `events` and `memory_summaries`, so this collection is always disposable and rebuildable.

## Proactive Channel

`proactive_messages` records are created by triggers: safety alert stored (actionable patient warning), first sighting of the day (morning report), time reminder due, and event-triggered reminder matched (a just-ingested camera event satisfies an active event reminder's room + time window + behavior condition; LLM condition matching is gated by `EVENT_REMINDER_LLM_MATCH` with a deterministic room+window fallback). Web Push is a wake-up channel only: an insert attempts delivery to enabled patient subscriptions, while `GET /proactive/pending` remains the sole atomic pending-to-delivered claim and the sole in-app renderer. Its payload now exposes the stored `related_id` so a rendered safety bubble can acknowledge the corresponding alert; the atomic claim semantics are unchanged. The React PWA polls every five seconds, immediately on a service-worker message, and acknowledges only after rendering. Geofence check-in messages are post-hackathon backlog; the existing geofence endpoints remain preserved contracts with no new behavior. The legacy FCM delivery code and `POST /devices/register` remain dormant compatibility surfaces after `Mobile/` removal.

## Critical Design Rules

- MongoDB is the only source of truth; Chroma must always be rebuildable from it.
- Memory is archived or consolidated, never erased.
- Patient-facing text never contains raw exception strings; failures log fully server-side and return a fixed reassuring message.
- Conversation memory is not monitoring evidence and is never embedded.
- `image_path` leaving the API is always a URL path.
- The `/query`, `/conversation/reset`, alert, geofence, `/devices/register`, `/storage`, and `/capture` contracts must not break; the PWA consumes the patient-facing subset while dormant compatibility surfaces remain intact.
- Capture stays functional standalone; spec 0010 will add opt-in cloud ingestion via `INGEST_URL`.

## Intentional Design Decisions — Preserve During Rebuild

Behaviors that look like bugs but are deliberate; do not "fix" them without a spec saying so:

- **Capture debounces** (spec 0004): the 2s no-person buffer before stopping a recording tolerates YOLO false negatives and brief frame exits; the 3.5s fall-persistence window, 0.50 confidence threshold, and once-per-recording fall-alert guard prevent alert spam. Make them env-tunable with the same defaults; treat the values as tuned, not arbitrary.
- **End-of-event screenshot** (spec 0004): the saved screenshot deliberately captures the room *after* the person leaves — the end state is the best evidence for object-finding and unattended-hazard checks.
- **fps=20 and default-microphone audio** (spec 0004): accepted hardware/single-occupant tradeoffs (two-room home, one active camera at a time). Do not add per-camera microphone plumbing; an optional `device_index` passthrough is the ceiling.
- **Gemini video fallback chain** (`GEMINI_VIDEO_FALLBACK_MODELS` + retry env vars, spec 0003): a workaround for flaky preview models; preserve the fallback chain wherever Gemini remains the video/spatial fallback.
- **Conversation memory in MongoDB** (spec 0006): a conscious reversal of the archived pre-rebuild rule, required for cross-session persistence. The two original boundaries still hold: chat turns are never embedded in Chroma and never treated as monitoring evidence.
- **Fall-alert targeting** (spec 0004): YOLO fall alerts intentionally target caretakers only. Patient-facing proactive warnings are created from actionable hazard alerts produced by the safety agent; do not redirect fall alerts to the patient channel.

Two implementation cautions for cleanups that *are* wanted: alert/index initialization must run once per process (alerts are created from both the API server and the capture pipeline process — FastAPI lifespan alone does not cover capture), and both `uvicorn Blue_dream_agents.api:app` and `python Capture/camera_feed.py` invocations must keep working after any import-pattern cleanup.

## DashScope Assumptions To Verify (spec 0005 spike, before dependent code)

1. Correct base URL for the account region (`dashscope-intl.aliyuncs.com` vs `dashscope.aliyuncs.com`) and availability of the target models (`qwen3.7-plus`, `qwen3-vl-plus`, `qwen3-vl-flash`; fallback ladder in spec 0005 requirements).
2. `response_format: json_object` support for `qwen3.7-plus` in compatible mode, plus its thinking-mode default and `enable_thinking: false` pass-through on non-streaming calls (latency matters — all text traffic runs on this model).
3. `text-embedding-v4` availability on the compatible-mode `/embeddings` endpoint, its `dimensions` parameter, and the per-request batch limit (chunk `embed_texts` accordingly).
4. Qwen-VL grounding output on `qwen3-vl-plus`: bounding-box coordinate convention (absolute pixels vs 0–1000 normalized) and reliability through compatible mode.
5. Video via OSS presigned URL: `oss2` upload + `sign_url` round-trip, then `qwen3-vl-flash` accepts the presigned URL as a `video_url` content part on the intl endpoint and answers about clip content; record the effective size/duration ceilings for our clips. Multi-image sequential input is verified for API evidence only and is not a production fallback.
6. ASR/TTS endpoint shapes: OpenAI-style `/audio/*` in compatible mode, or the native `dashscope` SDK (`qwen3-asr-flash` — incl. the `-filetrans` variant for stored files — and `qwen3-tts-flash`).

## Reference Documents

- `docs/FEATURE_STATUS.md` — the project ledger; check before starting work.
- `docs/specs/0001-...` through `docs/specs/0012-...` — per-feature requirements, design, tasks, status.
- `docs/DEPLOYMENT_ALIBABA.md` — cloud deployment walkthrough (stretch).
- `docs/SUBMISSIONS.md` — hackathon requirement checklists and video scripts.
- `docs/archive/` — pre-rebuild AGENTS/PLANS baselines (historical record of the earlier architecture).
