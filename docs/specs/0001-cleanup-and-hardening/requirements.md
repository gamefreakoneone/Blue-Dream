# 0001 Cleanup And Hardening Requirements

## Goal

Remove dead weight and fix the known correctness hazards so every later spec builds on a stable, testable baseline. This spec makes no feature changes and no API contract changes.

## Functional Requirements

- Delete dead code and clutter that no later spec depends on (LLM provider dead code is deleted in spec 0003 together with its replacement, not here).
- Pin every dependency in `requirements.txt` and add missing ones (`tzdata`, `pytest`).
- Patient-facing responses never contain raw exception text; full tracebacks are logged server-side.
- Gemini video analysis polling has a hard timeout so a stuck upload cannot wedge the ingestion queue.
- The timezone is configurable via a `TIMEZONE` env var (default remains `America/Los_Angeles`).
- FastAPI startup uses the lifespan API instead of the deprecated `@app.on_event("startup")`.
- A minimal pytest suite exists and passes, giving later specs a regression net.

### Additional findings from the 2026-07-16 audit (small, in scope)

- `ensure_alert_indexes()` is re-awaited at the top of nearly every `alert_service` function (e.g. `alert_service.py:216,239,253`) — replace with once-per-process initialization. Caution: alerts are created from **two processes** (the API server and the capture pipeline via the consolidator), so FastAPI lifespan alone does not cover capture; keep an idempotent per-process guard rather than lifespan-only.
- `close_http_client` / `close_mongo_client` exist but are never called — wire them into the lifespan shutdown added by this spec.
- `alert_service.choose_highlight_target` (`alert_service.py:48–56`) hardcodes demo keyword lists ("video game controller", xbox/playstation terms) in a safety path — trim to a generic hazard-first heuristic.
- Operational note (no code): root `.env` predates `.env.example` (May 18 vs Jul 14) — refresh it against `.env.example` before demos.

## Technical Constraints

- Python work runs in the `Project-Memoria` conda environment.
- No behavior change to `/query`, `/conversation/reset`, alert, or geofence endpoints beyond the error-text fix.
- Do not touch `Blue_dream_agents/llm/` provider internals (spec 0003 replaces them wholesale).
- Do not touch `Capture/camera_feed.py` logic (spec 0004 restructures it); only its Gmail dead-code dependency may shrink.

## Non-Requirements

- No package restructure, no renames of `Blue_dream_agents/` or `Capture/`.
- No new features.
- No mobile changes.

## Acceptance Criteria

- `python -m compileall -q Blue_dream_agents Capture` passes.
- `python -m pytest tests/` passes.
- A forced failure inside `/query` returns HTTP 200 with the fixed patient-safe message (or a generic HTTP error detail), never `str(exc)` content.
- `video_agent` polling exits with a timeout error after `VIDEO_ANALYSIS_TIMEOUT_SECONDS` and the consolidator still persists a partial event.
- Backend starts without deprecation warnings for startup events.
- `pip install -r requirements.txt` into a fresh environment succeeds on Windows (tzdata present).
- Deleted directories (`References/`, `Reference/`, `System/`) and dead Gmail machinery are gone; the fall-alert email send path still imports and works.
