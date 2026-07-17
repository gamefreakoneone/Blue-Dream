# 0001 Cleanup And Hardening Tasks

## Prerequisites

- [x] `Project-Memoria` conda environment active and working.
- [x] `git status` clean before starting; work on a fresh commit boundary.

## Implementation Tasks

- [x] Verify `References/`, `Reference/`, `System/` are untracked/empty, then delete them. (All three were already absent.)
- [x] Trim `Blue_dream_agents/Tools/dementia_email.py` to the Gmail auth + `send_alert_email` path; delete inbox monitoring, reply machinery, and interactive `main()`.
- [x] Remove unused `run_semantic_query` import and unused `decision` parameter in `Blue_dream_agents/jeeves.py`.
- [x] Pin all direct dependencies in `requirements.txt`; add `tzdata` and `pytest`.
- [x] Replace patient-facing `{exc}` text in `jeeves.py`, `time_agent.py`, `semantic_search.py` (both sites), and generic-ify `HTTPException` details in `api.py`; add `logger.exception` at each site.
- [x] Add polling deadline to `video_agent.py` with `VIDEO_ANALYSIS_TIMEOUT_SECONDS` (default 300).
- [x] Make `timezone_utils.py` read `TIMEZONE` from env; document in `.env.example`.
- [x] Migrate `api.py` startup hook to the lifespan API; wire `close_http_client` / `close_mongo_client` into lifespan shutdown.
- [x] Replace per-call `ensure_alert_indexes()` awaits in `alert_service.py` with idempotent once-per-process initialization (must also cover the capture-pipeline process, not just FastAPI lifespan).
- [x] Trim the hardcoded demo keyword lists in `alert_service.choose_highlight_target` to a generic hazard-first heuristic.
- [x] Create `tests/conftest.py`, `tests/test_api_contract.py`, `tests/test_error_messages.py`.

## Tests

- [x] `python -m compileall -q Blue_dream_agents Capture` passes.
- [x] `python -m pytest tests/ -q` passes.
- [x] Forced query failure returns the fixed patient-safe message (asserted in tests).
- [x] Simulated video-processing hang raises `TimeoutError` after the configured deadline (unit test with a stubbed client and a tiny timeout).

## Manual Checks

- [x] Backend starts with no `on_event` deprecation warning.
- [x] Live `/query` route smoke DEFERRED to spec 0005 (first live provider, Qwen). Optional legacy Nova check not required.
- [x] Fall-alert email import path still works (`GmailAgent` importable; send skipped gracefully without `FALL_ALERT_RECIPIENT_EMAIL`).

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md` and this spec's `status.md` with evidence.
- [x] Commit as a single spec-complete commit.
