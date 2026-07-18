# 0002 Media Path Service Tasks

## Prerequisites

- [x] Spec 0001 completed (pytest scaffold exists).

## Implementation Tasks

- [x] Create `Blue_dream_agents/media_paths.py` with `to_stored_path`, `to_fs_path`, `to_url_path`, `normalize_stored_path`, `resolve_output_dir`, `MEDIA_ROOT`.
- [x] Consolidator: store `to_stored_path` forms; dedupe compares normalized forms (legacy variants still match).
- [x] Capture: wrap queued screenshot/video/audio path values in `to_stored_path` (surgical change only).
- [x] Object detector: use `resolve_output_dir("Storage/highlighted")`; return URL-form `image_path`; resolve reads via `to_fs_path(normalize_stored_path(...))`.
- [x] Alert service: fix CWD-relative highlight dir via `resolve_output_dir`; store stored-form paths; serialize URL-form `image_path`/`original_image_path`; resolve reads via `to_fs_path`.
- [x] Safety agent: resolve screenshot reads via `to_fs_path(normalize_stored_path(...))`.
- [x] `gemini_spatial.py`: accept `Path` output dir; stop resolving bare relative strings against CWD.
- [x] `memory_schema.py`: normalize `screenshot_path`/`video_path`/`audio_path` in read-time normalization.
- [x] Grep all `image_path` assignments flowing into responses; convert to `to_url_path` at the API boundary.
- [x] `UI/script.js`: remove the substring rewrite; use `image_path` directly.
- [x] `Mobile/lib/api.js`: simplify to http-passthrough + base-URL prefix for leading-`/` paths.
- [x] `.env.example`: fix `CHROMA_PERSIST_DIR` guidance; document `MEDIA_ROOT`.

## Tests

- [x] `tests/test_media_paths.py` covering legacy Windows absolute, POSIX absolute, already-stored, `Capture/` paths, case-insensitivity, empty input, round-trip.
- [x] Contract test: mocked object query + alert detail return `/storage/...` URL paths.
- [x] Full suite passes: `python -m pytest tests/ -q`.

## Manual Checks

Note: checks needing live `/query` reasoning and ingestion transcription defer to spec 0005. That spec provides the first live Qwen reasoning and ASR gate; spec 0002 does not wait for an OpenAI transcription key.

- [ ] New ingested event doc in Mongo has relative POSIX paths.
  - Deferred to spec 0005 Qwen ASR live validation. The 2026-07-17 attempt using the old OpenAI path stopped before write and left Mongo unchanged.
- [x] Legacy event (absolute Windows path) still: resolves for internal reads, returns `/storage/...` in responses, renders in the web UI.
- [ ] Object question renders its highlighted image in the web UI without the old rewrite code (DEFERRED to spec 0005 — needs live reasoning).
- [ ] Alert detail image renders.
  - Blocked on 2026-07-17: Mongo contains four alerts and none has an `image_path`; no patient alert was fabricated for validation.
- [x] Highlight files created under project-root `Storage/highlighted/` when the backend is started from a different CWD.

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
