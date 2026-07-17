# 0005 Qwen Provider Design

## Contracts You Must Not Break

- All `/query` contracts and response shapes.
- Qwen is the default (and only) dev provider for the rebuild (`LLM_PROVIDER=qwen`); the spike must pass before any dependent code. Code paths must still fail with a clear config error — never a crash — when the DashScope key is absent.
- Other providers' Chroma collections are never modified.
- Semantic degradation rule: embedding failure → insufficient-evidence response, not a crash.

## Spike script: `scripts/dashscope_spike.py`

Standalone, reads `DASHSCOPE_API_KEY` (falling back to `QWEN_APIKEY`, the name in the local `.env`) and `DASHSCOPE_BASE_URL`, runs the seven checks from requirements sequentially, prints PASS/FAIL + raw payload snippets. Commit it — it is also Alibaba-API-usage evidence in the repo.

## Core wiring (mostly config, by design)

Spec 0003 built the machinery; this spec fills the `qwen` column with **spike-confirmed values**:

- `llm/settings.py` presets: correct base URL variant; the confirmed text/synthesis/vision/embedding model names; `supports_json_object` per the spike result.
- `llm/model_registry.py`: `qwen` targets resolve with `DASHSCOPE_API_KEY`; clear config error naming the var when absent.
- `embed_texts`: set the Qwen batch-size limit found in the spike (`EMBED_BATCH_SIZE` default per provider); pass `dimensions` if v4 honors it, else record the returned dim and set `LLM_EMBEDDING_DIM` accordingly.

## Transcription

- If compatible mode exposes `/audio/transcriptions`: `transcribe_audio` just works via the SDK — set the model name.
- Else: add `llm/dashscope_audio.py` (thin native `dashscope` SDK helper, executor-wrapped if synchronous) and route `TRANSCRIBE_PROVIDER=qwen` there. Pin `dashscope` in requirements. The native import doubles as Alibaba-service proof.
- `consolidator.py` needs no change — it calls `audio_transcribe`/`client.transcribe_audio` behind the provider switch.

## Stretch 1: Qwen-VL spatial grounding (`SPATIAL_PROVIDER=qwen`)

- New `Blue_dream_agents/spatial.py`: `async def localize_object(image_path, object_name) -> HighlightResult` dispatching on `SPATIAL_PROVIDER`.
  - `gemini` branch: delegate to the existing `gemini_spatial.py` (unchanged).
  - `qwen` branch: `invoke_multimodal_structured` on `qwen-vl-max` asking for `{"bbox_2d": [x1, y1, x2, y2], "label": ...}`; convert coordinates using the spike-confirmed convention (if 0–1000 normalized, scale by actual image dims; qwen-vl historically uses absolute pixels on the resized input — trust the spike, not folklore).
  - Rendering: reuse `gemini_spatial.py`'s box-drawing + save helpers — refactor `_save_highlighted_image` and the rectangle rendering into shared functions both branches call.
- `object_detector.py` and `alert_service.py` call `spatial.localize_object` instead of importing `gemini_spatial` directly.
- On any Qwen grounding failure: log + fall through to the Gemini branch when `GEMINI_API_KEY` is present (matches the third-party-fallback posture documented for the submission).

## Stretch 2: frame-sampled video (`VIDEO_PROVIDER=qwen`)

- `Blue_dream_agents/frame_sampler.py`: `sample_frames(video_path, n=12) -> list[Path]` — OpenCV, evenly spaced including first/last frames, JPEGs into a temp dir under `Storage/tmp_frames/` (cleaned after use).
- `video_agent.py` gains a provider switch: `qwen` → `client.invoke_video_structured(frame_paths=..., output_model=video_results)` with a "these are sequential frames from one room recording" instruction, same output model (`video_description`, `room_objects`, `danger_candidate`, `scene_end_state`, `observed_hazards`, `uncertainties`); `gemini` → existing path (with the 0001 timeout). Qwen failure → Gemini fallback when configured, else partial event (existing behavior).

## Config documentation

`.env.example` gains a commented "Qwen Cloud submission profile":

```ini
# LLM_PROVIDER=qwen
# EMBEDDING_PROVIDER=qwen
# TRANSCRIBE_PROVIDER=qwen
# SPATIAL_PROVIDER=qwen        # stretch; gemini fallback
# VIDEO_PROVIDER=qwen          # stretch; gemini fallback
# DASHSCOPE_API_KEY=...
# DASHSCOPE_BASE_URL=<spike-confirmed>
```

## Tests

- Extend `tests/test_registry.py`: qwen preset resolution, missing-key error.
- `tests/test_spatial_dispatch.py`: provider dispatch + coordinate conversion for both conventions (pure math, no network); Gemini-fallback trigger on qwen failure (mocked).
- `tests/test_frame_sampler.py`: sample count/order on a tiny generated clip (or skip-marked if OpenCV video write unavailable in CI).

## Validation Commands

```powershell
conda run -n Project-Memoria python scripts/dashscope_spike.py          # record results in status.md
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live with `LLM_PROVIDER=qwen EMBEDDING_PROVIDER=qwen` — **this is the first live end-to-end validation of the provider layer** (the checks deferred from spec 0003): `/query` × 4 route types; Chroma qwen collection built from Mongo (log the indexed count); one Qwen transcription run. Stretch: one screenshot highlight via Qwen-VL compared side-by-side with the Gemini output; one frame-sampled video description compared with the stored Gemini description.
