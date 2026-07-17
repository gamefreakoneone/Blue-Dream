# 0006 Durable Memory Tasks

## Prerequisites

- [ ] Specs 0001–0003 and 0005 completed (0005 required first — Qwen is the only live provider; all live checks in this spec run on `LLM_PROVIDER=qwen`).

## Implementation Tasks

- [ ] Rework `conversation_memory.py` onto Mongo (`conversation_sessions`), keeping public function names; overflow summarization + trim; closed-session handling; read cache.
- [ ] Create `profile_memory.py`: combined `TurnMemoryExtraction` structured model (facts + reminder), dedup decisions, cap enforcement, `render_profile_block()`.
- [ ] Create `reminder_service.py`: create/list/done/`get_due_reminders`, daily rollover.
- [ ] Wire post-response fire-and-forget extraction task in `api.py` (fully exception-isolated).
- [ ] Inject profile block into jeeves synthesis + general-chat prompts.
- [ ] Add the six new endpoints (JSON-safe serialization).
- [ ] Add Mongo indexes (`conversation_sessions.session_id` unique, `profile_facts.status+category`, `reminders.status+due_at`) to `db_client.ensure_indexes`.
- [ ] Document `CONVERSATION_MAX_TURNS`, `PROFILE_MAX_ACTIVE_FACTS` in `.env.example`.

## Tests

- [ ] `tests/test_durable_memory.py`: persistence, summarization trim, restart survival, reset exclusion, fact dedup paths, cap overflow, injection rendering, reminder extraction + due logic, endpoint contracts, extraction-failure isolation.
- [ ] Full suite passes.

## Manual Checks

- [ ] Restart-survival demo beat works end-to-end in the web UI.
- [ ] Fact stated in session A is used in fresh session B's answer.
- [ ] Duplicate fact statement does not duplicate the record.
- [ ] "Remind me to…" appears in `GET /reminders` with the right `due_at`.
- [ ] Legacy `{query}`-only requests unchanged.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
