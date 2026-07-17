# 0001 Cleanup And Hardening Tasks

## Prerequisites

- [ ] `Project-Memoria` conda environment active and working.
- [ ] `git status` clean before starting; work on a fresh commit boundary.

## Implementation Tasks

- [ ] Verify `References/`, `Reference/`, `System/` are untracked/empty, then delete them.
- [ ] Trim `Blue_dream_agents/Tools/dementia_email.py` to the Gmail auth + `send_alert_email` path; delete inbox monitoring, reply machinery, and interactive `main()`.
- [ ] Remove unused `run_semantic_query` import and unused `decision` parameter in `Blue_dream_agents/jeeves.py`.
- [ ] Pin all direct dependencies in `requirements.txt`; add `tzdata` and `pytest`.
- [ ] Replace patient-facing `{exc}` text in `jeeves.py`, `time_agent.py`, `semantic_search.py` (both sites), and generic-ify `HTTPException` details in `api.py`; add `logger.exception` at each site.
- [ ] Add polling deadline to `video_agent.py` with `VIDEO_ANALYSIS_TIMEOUT_SECONDS` (default 300).
- [ ] Make `timezone_utils.py` read `TIMEZONE` from env; document in `.env.example`.
- [ ] Migrate `api.py` startup hook to the lifespan API; wire `close_http_client` / `close_mongo_client` into lifespan shutdown.
- [ ] Replace per-call `ensure_alert_indexes()` awaits in `alert_service.py` with idempotent once-per-process initialization (must also cover the capture-pipeline process, not just FastAPI lifespan).
- [ ] Trim the hardcoded demo keyword lists in `alert_service.choose_highlight_target` to a generic hazard-first heuristic.
- [ ] Create `tests/conftest.py`, `tests/test_api_contract.py`, `tests/test_error_messages.py`.

## Tests

- [ ] `python -m compileall -q Blue_dream_agents Capture` passes.
- [ ] `python -m pytest tests/ -q` passes.
- [ ] Forced query failure returns the fixed patient-safe message (asserted in tests).
- [ ] Simulated video-processing hang raises `TimeoutError` after the configured deadline (unit test with a stubbed client and a tiny timeout).

## Manual Checks

- [ ] Backend starts with no `on_event` deprecation warning.
- [ ] Live `/query` route smoke DEFERRED to spec 0005 (first live provider, Qwen). Optional: run on the legacy Nova config if its credentials still work — not required.
- [ ] Fall-alert email import path still works (`GmailAgent` importable; send skipped gracefully without `FALL_ALERT_RECIPIENT_EMAIL`).

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` and this spec's `status.md` with evidence.
- [ ] Commit as a single spec-complete commit.
