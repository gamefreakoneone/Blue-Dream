# 0007 Memory Lifecycle Tasks

## Prerequisites

- [x] Specs 0003 and 0006 completed (provider layer + profile facts available).

## Implementation Tasks

- [x] Add lifecycle fields to `MemoryEvent` + read-time defaults + serialization.
- [x] Importance scoring call in `consolidator.py` (failure → 0.5 default); auto-pin safety-warning events.
- [x] Create `memory_lifecycle.py` with `run_consolidation` (grouping, deterministic summary ids, per-group failure isolation, report).
- [x] `POST /memory/consolidate` endpoint + optional `CONSOLIDATE_ON_STARTUP` sweep.
- [x] Chroma sync/rebuild filters: active events + summaries; consolidated events excluded; summary hydration in retrieval.
- [x] `pack_recall` in `prompt_budget.py`; wire scored budgeted packing into the semantic retrieval path; emit `data.recall_debug`.
- [x] Pin/unpin endpoints for events (pin re-activates consolidated events).
- [x] UI "Memory used" collapsible panel.
- [x] Document the six new env vars in `.env.example`.

## Tests

- [x] `tests/test_recall_packing.py`: stale-vs-fresh regression, pinned inclusion, budget exclusion, empty input.
- [x] `tests/test_lifecycle.py`: grouping, idempotency, failure isolation, status flips, rebuild filtering, legacy defaults, importance-failure default, safety auto-pin.
- [x] Full suite passes.

## Manual Checks

- [x] Consolidation collapses a mundane day into one summary; report accurate; re-run is a no-op.
- [x] Semantic "what was I doing <day>?" grounds on the summary; pinned event still individually recallable.
- [x] Stale-event scenario: fresh event outranks the older higher-similarity one.
- [x] `recall_debug` visible in response `data` and rendered in the UI panel.
- [x] Time-agent date query still sees raw events for the consolidated day.

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
