# 0005 Qwen Provider Design

## Contracts You Must Not Break

- All `/query` contracts and response shapes.
- Qwen is the default (and only) dev provider for the rebuild (`LLM_PROVIDER=qwen`); the spike must pass before any dependent code. Code paths must still fail with a clear config error — never a crash — when the DashScope key is absent.
- Other providers' Chroma collections are never modified.
- Semantic degradation rule: embedding failure → insufficient-evidence response, not a crash.

## Spike script: `scripts/dashscope_spike.py`

Standalone, reads `DASHSCOPE_API_KEY` (falling back to `QWEN_APIKEY`, the name in the local `.env`), `DASHSCOPE_BASE_URL`, and the `OSS_*` vars, runs the ten checks from requirements sequentially, prints PASS/FAIL + raw payload snippets. Commit it — it is Alibaba-API-usage evidence for both DashScope and OSS in the repo.

## Core wiring (mostly config, by design)

Spec 0003 built the machinery; this spec fills the `qwen` column with **spike-confirmed values**. Targets (per the requirements Goal): text/synthesis `qwen3.7-plus`, vision/video `qwen3-vl-flash`, spatial `qwen3-vl-plus`, embedding `text-embedding-v4`, transcribe `qwen3-asr-flash` — falling down the documented availability ladder if the spike finds a model missing.

- `llm/settings.py` presets: correct base URL variant; the confirmed text/synthesis/vision/video/spatial/embedding model names; `supports_json_object` per the spike result; thinking-mode handling (`enable_thinking: false` via `extra_body`, or whatever the spike confirms) for latency-sensitive routing/judging calls if `qwen3.7-plus` defaults to thinking on.
- `llm/model_registry.py`: update the qwen preset defaults (currently `qwen-plus`/`qwen-max`/`qwen-vl-max`) to the spike-confirmed models, and update the matching assertions in `tests/test_registry.py`. `tests/test_vector_store_providers.py` is unaffected (embedding model unchanged). `qwen` targets resolve with `DASHSCOPE_API_KEY`; clear config error naming the var when absent.
- `embed_texts`: set the Qwen batch-size limit found in the spike (`EMBED_BATCH_SIZE` default per provider); pass `dimensions` if v4 honors it, else record the returned dim and set `LLM_EMBEDDING_DIM` accordingly.

## Transcription

- If compatible mode exposes `/audio/transcriptions`: `transcribe_audio` just works via the SDK — set the model name.
- Else: add `llm/dashscope_audio.py` (thin native `dashscope` SDK helper, executor-wrapped if synchronous) and route `TRANSCRIBE_PROVIDER=qwen` there. Pin `dashscope` in requirements. The native import doubles as Alibaba-service proof.
- `consolidator.py` needs no change — it calls `audio_transcribe`/`client.transcribe_audio` behind the provider switch.

## Core: Qwen-VL spatial grounding (`SPATIAL_PROVIDER=qwen`)

(First cut lever if the schedule slips: skip the qwen branch and stay on the Gemini fallback.)

- New `Blue_dream_agents/spatial.py`: `async def localize_object(image_path, object_name) -> HighlightResult` dispatching on `SPATIAL_PROVIDER`.
  - `gemini` branch: delegate to the existing `gemini_spatial.py` (unchanged).
  - `qwen` branch: `invoke_multimodal_structured` on `qwen3-vl-plus` (the documented high-precision 2D/3D localization model) asking for `{"bbox_2d": [x1, y1, x2, y2], "label": ...}`; convert coordinates using the spike-confirmed convention (if 0–1000 normalized, scale by actual image dims; qwen-vl historically uses absolute pixels on the resized input — trust the spike, not folklore).
  - Rendering: reuse `gemini_spatial.py`'s box-drawing + save helpers — refactor `_save_highlighted_image` and the rectangle rendering into shared functions both branches call.
- `object_detector.py` and `alert_service.py` call `spatial.localize_object` instead of importing `gemini_spatial` directly.
- On any Qwen grounding failure: log + fall through to the Gemini branch when `GEMINI_API_KEY` is present (matches the third-party-fallback posture documented for the submission).

## Core: OSS-URL video understanding (`VIDEO_PROVIDER=qwen`)

- New `Blue_dream_agents/oss_media.py` (SDK: `oss2`, pinned in `requirements.txt` in the same change):
  - `upload_video(fs_path) -> object_key` — object key mirrors the stored relative POSIX path (derivable from `video_path`); skip re-upload when the key already exists in the bucket.
  - `presigned_url(object_key, ttl=OSS_PRESIGN_TTL_SECONDS) -> str` — `bucket.sign_url("GET", ...)`; the bucket stays private.
  - Config from `OSS_ACCESS_KEY_ID`/`OSS_ACCESS_KEY_SECRET`/`OSS_BUCKET`/`OSS_ENDPOINT`; missing config raises a clear error the callers catch to fall back — never a crash, never an ingestion blocker.
- `consolidator.py`: before the video-understanding call, upload the finished recording and store the returned `video_oss_key` on the `MemoryEvent` (optional field, absent on legacy documents).
- `video_agent.py` gains a provider switch: `qwen` → presigned URL from `oss_media` → `client.invoke_video_structured(video_url=..., output_model=video_results)`, same output model (`video_description`, `room_objects`, `danger_candidate`, `scene_end_state`, `observed_hazards`, `uncertainties`); `gemini` → existing path (with the 0001 timeout).
- Fallback ladder on the qwen branch: any OSS upload/presign or Qwen URL-video failure → existing full-video Gemini analysis when configured → partial event (existing behavior). Frame sampling is intentionally excluded so long recordings retain full temporal context.

## Config documentation

`.env.example` gains a commented "Qwen Cloud submission profile":

```ini
# LLM_PROVIDER=qwen
# EMBEDDING_PROVIDER=qwen
# TRANSCRIBE_PROVIDER=qwen
# SPATIAL_PROVIDER=qwen        # gemini fallback on failure
# VIDEO_PROVIDER=qwen          # OSS-URL primary; full-video Gemini fallback
# DASHSCOPE_API_KEY=...
# DASHSCOPE_BASE_URL=<spike-confirmed>
# OSS_ACCESS_KEY_ID=...
# OSS_ACCESS_KEY_SECRET=...
# OSS_BUCKET=memoria
# OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
# OSS_PRESIGN_TTL_SECONDS=3600
```

## Tests

- Extend `tests/test_registry.py`: qwen preset resolution, missing-key error.
- `tests/test_oss_media.py`: object-key derivation from `video_path`, missing-config error, presign call shape (mocked `oss2`, no network); video-agent direct Gemini fallback on OSS/Qwen failure (mocked).
- `tests/test_spatial_dispatch.py` (required): provider dispatch + coordinate conversion for both conventions (pure math, no network); Gemini-fallback trigger on qwen failure (mocked).

## Validation Commands

```powershell
conda run -n Project-Memoria python scripts/dashscope_spike.py          # record results in status.md
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live with `LLM_PROVIDER=qwen EMBEDDING_PROVIDER=qwen` — **this is the first live end-to-end validation of the provider layer** (the checks deferred from spec 0003): privacy-safe textual `/query` routes; Chroma qwen collection from Mongo only when the execution environment permits authorized existing-memory export; one production Qwen transcription; one genuine stored video through the OSS-URL path; and one visually inspected screenshot highlight via Qwen-VL (`qwen3-vl-plus`). Do not insert unmatched media as a memory merely to satisfy validation. Per user direction, do not send the selected media to Gemini for a live comparison; mocked fallback coverage is sufficient.
