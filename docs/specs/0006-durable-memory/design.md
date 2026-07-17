# 0006 Durable Memory Design

## Contracts You Must Not Break

- `POST /query` request/response shapes; `session_id` remains optional; `POST /conversation/reset` returns `{"ok": true}`.
- `jeeves.py` context contract: object/time/semantic tools receive the resolved standalone query only; full conversation context is used solely for follow-up rewriting and general chat.
- Conversation memory is never embedded in Chroma and never used as monitoring evidence.

## Conversation memory: rework `Blue_dream_agents/conversation_memory.py`

Keep the module name and public functions (`get_context`, `append_turn`, `reset_session` — match current names) so `api.py`/`jeeves.py` changes stay minimal; swap the in-process dict for Mongo via `db_client`:

- `append_turn(session_id, role, text)` → `$push` turn + `$set last_active_at`; upsert.
- After appending, if `len(turns) > CONVERSATION_MAX_TURNS`: take the overflow oldest turns, one `invoke_structured` summarization call (merge with existing `summary`), `$set summary`, trim `turns` to the recent window. Summarization failure → keep untrimmed turns (correctness over compaction).
- `get_context(session_id)` → render `summary` (prefixed "Earlier in this conversation:") + recent turns, respecting the existing char budget (~4000).
- `reset_session(session_id)` → `$set status: "closed"`; context reads exclude closed sessions.
- Keep a small in-process read cache per session (dict, cleared on write) to avoid a Mongo round-trip on every context render; correctness comes from Mongo, the cache is an optimization.

## Profile facts: new `Blue_dream_agents/profile_memory.py`

```python
class ProfileFactExtraction(BaseModel):
    facts: list[ExtractedFact]        # {category, text, confidence}
class FactDedupDecision(BaseModel):
    action: Literal["add", "update", "skip"]
    target_fact_id: str | None
    merged_text: str | None
```

- `extract_and_store(user_text, assistant_text)` — called post-response from `api.py` as `asyncio.create_task(...)` wrapped in a try/except-log; one extraction call (prompt: "stable personal facts only — people, preferences, routines, medical, safety; ignore transient states"); for each fact, one dedup call against active same-category facts (they fit in one prompt at ≤50 facts).
- `get_active_facts()` — pinned first, then confidence desc; rendered by `render_profile_block()` as the "What you know about the patient" prompt section.
- `jeeves.py` injection points: the semantic synthesis prompt builder and the general-chat prompt builder get `render_profile_block()` prepended (after the shared `prompt_context.py` prefix). Keep the block clearly delimited so prompts stay auditable.
- Cap enforcement on insert; archive lowest-confidence unpinned overflow.

## Reminders: new `Blue_dream_agents/reminder_service.py`

- `ReminderExtraction(BaseModel)`: `{is_reminder: bool, text: str | None, due_at: datetime | None, recurrence: Literal["none","daily"]}` — extraction prompt includes "now" (project timezone) so "at 8" resolves to the next 8:00.
- Extraction piggybacks the same post-response task as profile facts (one combined structured call is acceptable — `TurnMemoryExtraction` with both `facts` and `reminder` fields — one LLM call per turn, not two; design the Pydantic model that way).
- `create_reminder`, `list_active`, `mark_done`, `get_due_reminders(now)` (status active, `due_at <= now`; for `daily`, roll `due_at` forward on delivery — 0008 calls this).

## API additions (`api.py`)

```
GET  /memory/profile                    -> {"facts": [ {fact_id, category, text, confidence, pinned, status, created_at} ]}
POST /memory/profile/{fact_id}/pin      -> {"ok": true}
POST /memory/profile/{fact_id}/archive  -> {"ok": true}
GET  /reminders                         -> {"reminders": [...]}
POST /reminders                         -> create {text, due_at, recurrence?}
POST /reminders/{reminder_id}/done      -> {"ok": true}
```

All JSON-safe (no ObjectId leakage — follow the existing alert-serialization pattern). Indexes added in `db_client.ensure_indexes`.

## Failure isolation

The post-response extraction task must be fully isolated: any exception logs and dies silently; `/query` latency and response are unaffected. Add a regression test asserting the response returns even when extraction raises.

## Tests (`tests/test_durable_memory.py`)

Use mongomock-style stubbing or a monkeypatched motor collection (follow whatever pattern 0001's conftest established; a thin fake-collection class is acceptable):

- Turn persistence, overflow summarization trim (mocked LLM), restart survival (new store instance, same fake collection).
- Closed-session exclusion after reset; legacy no-session flow untouched.
- Fact extraction→store, dedup update vs add vs skip (mocked decisions), cap-overflow archiving, injection block rendering (pinned first).
- Reminder extraction true/false cases; `get_due_reminders` boundary; daily rollover.
- Endpoint contract tests for the six new routes.
- Extraction-failure isolation test.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live demo-beat rehearsal: start backend → chat two turns → kill backend → restart → follow-up question resolves; state a personal fact → new browser session → question answered using the fact; "remind me to…" → visible in `GET /reminders`.
