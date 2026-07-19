# 0008a Audit Cleanup Tasks

## Prerequisites

- [x] Read this spec's `requirements.md` and `design.md` fully.
- [x] Specs 0001–0008 are implementation-complete for this cleanup prerequisite; no prior spec was reworked.

## Implementation Tasks

- [x] A1: `proactive_service.create_message` persists `to_stored_path(image_path)`; `/proactive/pending` serialization converts via `to_url_path(normalize_stored_path(...))`.
- [x] A2: reminder working-memory renderer (today's active time + event reminders, ≤5 lines, plain Mongo read); injected into general-chat, semantic-synthesis, and insufficient-evidence prompts alongside profile facts; failure omits the block silently.
- [x] A3: profile-fact block (and A2 reminder block) added to object-search and time-window answer prompts.
- [x] A4: `alert_service` delivery failures store/return a fixed short string in `delivery_details`; full exception only in logs (both send-failure sites).
- [x] A5: consolidator safety-assessment failure uses fixed reason "Safety assessment unavailable for this recording."; traceback logged.
- [x] A6: duplicate-ingest path skips `index_memory_event` when the existing event is `consolidated`.
- [x] A7: split `mark_done` semantics — proactive delivery keeps daily roll-forward; `POST /reminders/{id}/done` completes/archives daily reminders.
- [x] A8: `testpaths = tests` pytest config; bare `pytest` from root collects only `tests/`.
- [x] A9: `gemini_spatial` reuses the shared JSON-hardening helpers from the provider layer; local duplicates removed; parsed output unchanged.
- [x] A10: `run_semantic_query` is docstring-marked smoke-test-only.
- [x] A11: `oss_media.presigned_url(object_key, ttl=None)` with settings default and existing bounds check.
- [x] A12: `Capture/audio_capture.py` `__main__` maps `device_index=-1` → `None`.
- [x] B1: `TECHNICAL_DESIGN.md` — `INGEST_URL` phrased as spec 0010 planned capability.
- [x] B2: `TECHNICAL_DESIGN.md` Intentional Design Decisions — fall alerts are caretaker-targeted by design; patient proactive warnings come from safety-agent hazard alerts.
- [x] B3: `TECHNICAL_DESIGN.md` env surface — add `LLM_SYNTHESIS_MODEL`, `LLM_TRANSCRIBE_MODEL`, `LLM_TTS_MODEL`, `EMBED_BATCH_SIZE`, `GEMINI_SPATIAL_MODEL`, `LLM_DEFAULT_TEMPERATURE`, `LLM_DEFAULT_MAX_TOKENS`, `LLM_REQUEST_TIMEOUT_SECONDS`.

## Tests

- [x] Proactive message with image: stored form in Mongo, URL form in `/proactive/pending` response; legacy URL-form document still serializes correctly.
- [x] Reminder block appears in the general-chat prompt context when a due-today reminder exists (mocked LLM; assert prompt content).
- [x] `POST /reminders/{id}/done` completes a daily reminder; proactive delivery of a daily reminder still rolls `due_at` forward.
- [x] Duplicate ingest of a `consolidated` event does not re-index into Chroma.
- [x] `delivery_details` failure entries contain the fixed string, not exception text.
- [x] Collection guard: bare `pytest` from repo root collects only `tests/` (asserted via `pytest --collect-only -q` in a subprocess and the required manual command).
- [x] Full suite: `python -m pytest tests/ -q` — 129 passed, zero failures/errors (`Project-Memoria` conda env).

## Manual Checks

- [x] Isolated backend: a due-today reminder plus "what do I need to do today?" returned "Today, you need to call Sarah about the family visit."
- [x] Proactive image boundary: isolated Mongo stored `Storage/...`, `/proactive/pending` returned `/storage/...`, and the static image returned HTTP 200. The UI renderer is unchanged and has independent rendered evidence from spec 0008; a fresh screenshot was unavailable because the installed Browser plugin lacks its required runtime file.
- [x] `python Capture/camera_feed.py` stayed alive through 15 seconds of startup/import and was then stopped cleanly.

## Wrap-Up

- [x] Update this spec's `status.md` with pytest summary and manual-check evidence; check off tasks here.
- [x] Update `docs/FEATURE_STATUS.md` (0008a → Completed, evidence + this commit/`HEAD`).
- [x] Single descriptive commit containing implementation, tests, and docs.
