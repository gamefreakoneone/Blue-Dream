# 0006 Durable Memory Status

## Status

Completed 2026-07-18. Durable conversations, profile facts, and time/event
reminders are implemented and verified offline and against live Qwen. The
implementation commit hash will be recorded by the follow-up evidence commit.

## Verification Evidence

- Starting baseline: `conda run -n Project-Memoria python -m pytest tests/ -q`
  passed with **74 tests** and two existing dependency warnings.
- Required final validation: `conda run -n Project-Memoria python -m pytest
  tests/ -q` passed with **87 tests** and the same two dependency warnings
  (`StarletteDeprecationWarning` and Python 3.13 `audioop` deprecation). Conda's
  known non-fatal missing OpenCL `temp.txt` cleanup message remains unchanged.
- `tests/test_durable_memory.py`: **13 passed**. Coverage includes Mongo turn
  persistence, a new store instance reading the same collection, summary trim
  success/failure, reset exclusion, cache invalidation, combined extraction,
  add/update/skip dedup, exact-turn idempotency across category drift, cap
  archiving, pinned-first rendering, profile-aware semantic fallback, both
  reminder kinds, due/date/window/overnight boundaries, daily rollover, indexes,
  six endpoint contracts, JSON round trips, 404/422 behavior, and extraction
  failure isolation.
- Live command: `powershell.exe -ExecutionPolicy Bypass -File
  scripts/run_spec0006_rehearsal.ps1` passed against `LLM_PROVIDER=qwen` and a
  real stopped/restarted FastAPI process. It verified restart-surviving context,
  fresh-session profile recall, duplicate suppression, legacy `{query}` input,
  a time reminder resolved to `2026-07-19T08:00:00-07:00`, and an event reminder
  resolved to `valid_date=2026-07-19`, window `06:00-11:00`, with a non-empty
  behavior condition.
- The live script redirects synthetic records into three dedicated
  `spec0006_smoke_*` collections. Post-run verification found **0 documents** in
  all three collections and no listener on port 8016; production collections
  were never used for smoke data.
- Live-model hardening found and fixed two edge cases: exact repeated turns can
  drift between allowed fact categories, so a normalized turn fingerprint makes
  exact retries idempotent; profile questions routed to semantic recall now use
  durable profile facts when monitoring evidence is insufficient, without
  treating conversation history as monitoring evidence.
- No spec 0007 implementation or status change was made.
- Implementation commit: pending.
