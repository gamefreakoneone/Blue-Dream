# 0007 Memory Lifecycle Tasks

## Prerequisites

- [ ] Specs 0003 and 0006 completed (provider layer + profile facts available).

## Implementation Tasks

- [ ] Add lifecycle fields to `MemoryEvent` + read-time defaults + serialization.
- [ ] Importance scoring call in `consolidator.py` (failure → 0.5 default); auto-pin safety-warning events.
- [ ] Create `memory_lifecycle.py` with `run_consolidation` (grouping, deterministic summary ids, per-group failure isolation, report).
- [ ] `POST /memory/consolidate` endpoint + optional `CONSOLIDATE_ON_STARTUP` sweep.
- [ ] Chroma sync/rebuild filters: active events + summaries; consolidated events excluded; summary hydration in retrieval.
- [ ] `pack_recall` in `prompt_budget.py`; wire scored budgeted packing into the semantic retrieval path; emit `data.recall_debug`.
- [ ] Pin/unpin endpoints for events (pin re-activates consolidated events).
- [ ] UI "Memory used" collapsible panel.
- [ ] Document the six new env vars in `.env.example`.

## Tests

- [ ] `tests/test_recall_packing.py`: stale-vs-fresh regression, pinned inclusion, budget exclusion, empty input.
- [ ] `tests/test_lifecycle.py`: grouping, idempotency, failure isolation, status flips, rebuild filtering, legacy defaults, importance-failure default, safety auto-pin.
- [ ] Full suite passes.

## Manual Checks

- [ ] Consolidation collapses a mundane day into one summary; report accurate; re-run is a no-op.
- [ ] Semantic "what was I doing <day>?" grounds on the summary; pinned event still individually recallable.
- [ ] Stale-event scenario: fresh event outranks the older higher-similarity one.
- [ ] `recall_debug` visible in response `data` and rendered in the UI panel.
- [ ] Time-agent date query still sees raw events for the consolidated day.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
