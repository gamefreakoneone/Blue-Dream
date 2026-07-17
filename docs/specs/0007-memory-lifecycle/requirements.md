# 0007 Memory Lifecycle Requirements

## Goal

Give the memory system a lifecycle — importance at birth, consolidation in old age, pinning for what must never fade — and make recall rank by relevance × recency × importance within a token budget. Together these fix the known stale-event recall bug and implement the MemoryAgent track's "timely forgetting of outdated information" and "recalling critical memories within limited context windows."

**Framing (use in prompts, README, and demo): the agent practices memory hygiene so the patient never has to. Patient memories are consolidated and archived, never erased.**

## Functional Requirements

### Importance at ingest

- During consolidation of a new event, one structured LLM call assigns `importance` (0.0–1.0) + `importance_reason` using a fixed rubric: safety hazards, falls, medical, and social interactions high (≥0.7); ordinary activity medium (~0.4–0.6); idle pass-throughs low (≤0.3).
- Scoring failure defaults to `importance=0.5` and never blocks event persistence.
- `MemoryEvent` gains: `importance`, `importance_reason`, `pinned` (bool), `lifecycle_status` (`active | consolidated`), `consolidated_into` (summary id or null). Legacy docs normalize at read time to `importance=0.5, pinned=false, lifecycle_status="active"`.

### Consolidation ("cleanup, never erasure")

- `POST /memory/consolidate` (and an optional startup sweep behind `CONSOLIDATE_ON_STARTUP=false`) groups **active, unpinned, low-importance** (`importance < CONSOLIDATION_IMPORTANCE_MAX`, default 0.5) events **older than `CONSOLIDATION_AGE_DAYS`** (default 2) by calendar day + room.
- Each group with ≥ `CONSOLIDATION_MIN_EVENTS` (default 3) is summarized by one LLM call into a `memory_summaries` document: `{summary_id, period: "day", date, room_number, room_name, text, source_event_ids, created_at}`.
- The summary is embedded into the active Chroma collection (as a summary-type entry); the source events are **removed from Chroma** and marked `lifecycle_status="consolidated"`, `consolidated_into=summary_id` in MongoDB. **No Mongo document is ever deleted.**
- The time agent (Mongo-direct) is unaffected: date-specific questions still see raw events.
- The endpoint returns a report: groups formed, events consolidated, summaries created.

### Pinning

- `POST /memory/events/{event_id}/pin` and `/unpin`. Pinned events are exempt from consolidation and receive guaranteed inclusion in recall packing.
- Profile facts already support pinning (0006); recall packing honors both.

### Context-budgeted recall

- Semantic recall re-ranks Chroma candidates: `final_score = similarity × exp(-age_days / RECALL_HALF_LIFE_DAYS) × (1 + importance)`; `RECALL_HALF_LIFE_DAYS` default 14.
- Packing order into `RECALL_TOKEN_BUDGET` (default 2000 tokens, chars/4 heuristic): pinned profile facts → pinned events → scored candidates descending. Items that don't fit are excluded, never truncated mid-record.
- The response's `data.recall_debug` lists, for each packed memory: id, type (event/summary/fact), timestamp, similarity, final_score, and whether pinned; plus counts of considered vs packed.
- The web UI renders a collapsible "Memory used" panel from `recall_debug` under assistant answers that carry it.

## Technical Constraints

- Recency/importance re-ranking applies to the semantic path; the time agent's window queries keep chronological order (its correctness is time-based, not relevance-based).
- Consolidation must be idempotent: re-running produces no new summaries for already-consolidated groups.
- Chroma remains rebuildable: rebuilding from Mongo indexes active events + summaries and skips consolidated events.

## Non-Requirements

- No weekly/monthly summary tiers (day-level only).
- No automatic pinning heuristics (manual + safety-event default: events with `warning_needed=true` safety assessments are ingested with `pinned=true`).
- No scheduler/cron; consolidation is on-demand (+ optional startup sweep).

## Acceptance Criteria

- The stale-event scenario passes: with an older high-similarity event and a fresh moderately-similar event about the same object, the fresh event ranks first and drives the answer.
- Consolidation demo: a day of ≥3 low-importance events collapses into one summary; the summary answers "what was I doing Tuesday?" via semantic recall; a pinned event from the same day survives individually; re-running consolidates nothing new.
- Chroma rebuild-from-Mongo yields active events + summaries only.
- `recall_debug` appears in semantic responses and renders in the UI panel.
- pytest covers scoring math, packing order/budget, consolidation grouping + idempotency, read-time lifecycle defaults, rebuild filtering.
