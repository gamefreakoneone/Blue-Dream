# 0007 Memory Lifecycle Design

## Contracts You Must Not Break

- `JeevesResponse` shape (`recall_debug` goes inside the existing `data` object field).
- MongoDB documents are never deleted; consolidation only flips `lifecycle_status` and removes Chroma entries.
- Time-agent behavior: Mongo-direct window queries see all events (active + consolidated) in chronological order.
- Semantic degradation rule unchanged.

## Schema (`memory_schema.py`)

Add to `MemoryEvent`: `importance: float = 0.5`, `importance_reason: str = ""`, `pinned: bool = False`, `lifecycle_status: str = "active"`, `consolidated_into: str | None = None`. Read-time normalization supplies these defaults for legacy docs (same mechanism as existing fallbacks). Serialization includes them on write.

## Importance at ingest (`consolidator.py`)

After video/audio results merge, before Mongo insert:

```python
class ImportanceAssessment(BaseModel):
    importance: float          # 0.0–1.0
    importance_reason: str
```

One `invoke_structured` call with the rubric prompt (input: `semantic_text` + safety fields). Wrap in try/except → default 0.5 / "scoring unavailable". If the safety agent set `warning_needed=true`, force `pinned=True` at ingest (safety events never fade).

## Consolidation (`Blue_dream_agents/memory_lifecycle.py`)

```python
async def run_consolidation(now=None) -> ConsolidationReport
```

1. Query: `lifecycle_status="active"`, `pinned=False`, `importance < CONSOLIDATION_IMPORTANCE_MAX`, `timestamp < now - CONSOLIDATION_AGE_DAYS` (project timezone day boundaries).
2. Group by (local date, room_number); skip groups smaller than `CONSOLIDATION_MIN_EVENTS`.
3. Per group: one `invoke_structured` summary call (input: the events' semantic_texts, prompt-budgeted via `prompt_budget`); insert `memory_summaries` doc with `summary_id = f"sum_{date}_{room}"` (deterministic → idempotency: skip groups whose summary_id already exists).
4. Chroma: upsert the summary (id `summary_id`, metadata `{type: "summary", date, room}`); delete the source event ids from the collection.
5. Mongo: `$set lifecycle_status="consolidated", consolidated_into=summary_id` on sources.
6. Failure isolation per group: one group's LLM failure skips that group, others proceed; report lists successes/failures.

`POST /memory/consolidate` (api.py) calls it and returns the report. `CONSOLIDATE_ON_STARTUP` (default false) runs it in the lifespan hook, exception-tolerant.

## Chroma sync filter (`semantic_search.py`)

`ensure_semantic_index_synced` / full rebuild: index events where `lifecycle_status="active"` plus all `memory_summaries`; skip consolidated events. Count-drift comparison uses (active events + summaries) as the expected total. Summary entries carry their `text` as the embedded document; retrieval treats a summary hit like an event hit with `type="summary"` (fetch from `memory_summaries` by id when hydrating).

## Scored, budgeted recall

Extend `prompt_budget.py` with a pure function (unit-test target):

```python
def pack_recall(candidates: list[RecallCandidate], *, token_budget: int,
                half_life_days: float, now: datetime) -> RecallPack
# RecallCandidate: {id, type, text, timestamp, similarity, importance, pinned}
# final_score = similarity * exp(-age_days/half_life_days) * (1 + importance)
# order: pinned facts, pinned events, scored desc; whole items only, chars//4 token estimate
# RecallPack: {included: [...], excluded_count, considered_count}
```

`semantic_search.py` retrieval path: hydrate Chroma hits from Mongo (existing flow) → build candidates (events, summaries) → add pinned profile facts from `profile_memory.get_active_facts()` (pinned only; unpinned facts are already injected globally by 0006 — do not double-inject) → `pack_recall` → evidence prompt built from `RecallPack.included` → `data.recall_debug` serialized from the pack (id, type, timestamp ISO, similarity, final_score rounded, pinned, plus counts).

## Pin endpoints (`api.py`)

`POST /memory/events/{event_id}/pin` / `/unpin` → `$set pinned` on the event; if the event was consolidated, pinning also re-activates it (`lifecycle_status="active"`, re-embed into Chroma) so a pinned memory is always individually recallable.

## UI panel (`UI/script.js` + `styles.css`)

When `data.recall_debug` exists on a response: render a collapsed `<details>` block "🧠 Memory used (N of M considered)" under the answer bubble listing type icon, date, score bar, pin marker per included memory. Text-only, escape all content.

## Env (document in `.env.example`)

`CONSOLIDATION_AGE_DAYS=2`, `CONSOLIDATION_IMPORTANCE_MAX=0.5`, `CONSOLIDATION_MIN_EVENTS=3`, `CONSOLIDATE_ON_STARTUP=false`, `RECALL_HALF_LIFE_DAYS=14`, `RECALL_TOKEN_BUDGET=2000`.

## Tests (`tests/test_lifecycle.py`, `tests/test_recall_packing.py`)

- `pack_recall`: stale-vs-fresh ordering (the original bug as a named regression test), pinned guaranteed inclusion, budget exclusion of whole items, empty candidates.
- Consolidation grouping (day/room boundaries in project timezone), min-group skip, deterministic summary_id idempotency, per-group failure isolation (mocked LLM), Mongo status flips, Chroma delete/upsert calls (mocked store).
- Read-time defaults for legacy docs.
- Rebuild filtering: consolidated events excluded, summaries included.
- Importance-failure default; safety-event auto-pin.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live: seed/choose a day with several mundane events → `POST /memory/consolidate` → verify report, Mongo statuses, Chroma contents; ask "what was I doing on <that day>?" (semantic) → summary-grounded answer; ask about the pinned event → individual recall; stale-event scenario against real data; UI memory panel renders.
