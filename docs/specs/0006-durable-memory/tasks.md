# 0006 Durable Memory Tasks

## Prerequisites

- [x] Specs 0001–0003 and 0005 implementation dependencies are available (0002's remaining ledger item is an unrelated unavailable image-bearing alert render); live checks ran on `LLM_PROVIDER=qwen`.

## Implementation Tasks

- [x] Rework `conversation_memory.py` onto Mongo (`conversation_sessions`), keeping public function names; overflow summarization + trim; closed-session handling; read cache.
- [x] Create `profile_memory.py`: combined `TurnMemoryExtraction` structured model (facts + reminder), dedup decisions, cap enforcement, `render_profile_block()`.
- [x] Create `reminder_service.py`: create/list/done for both trigger kinds (`time` | `event`), `origin_context` on chat-created reminders, `get_due_reminders` + daily rollover, `get_matchable_event_reminders(now)` pre-filter for 0008.
- [x] Wire post-response fire-and-forget extraction task in `api.py` (fully exception-isolated).
- [x] Inject profile block into jeeves synthesis + general-chat prompts.
- [x] Add the six new endpoints (JSON-safe serialization).
- [x] Add Mongo indexes (`conversation_sessions.session_id` unique, `profile_facts.status+category`, `reminders.status+due_at`, `reminders.status+trigger_type`) via per-collection `ensure_*_indexes` helpers following the existing `db_client.py` pattern.
- [x] Document `CONVERSATION_MAX_TURNS`, `PROFILE_MAX_ACTIVE_FACTS` in `.env.example`.

## Tests

- [x] `tests/test_durable_memory.py`: persistence, summarization trim, restart survival, reset exclusion, fact dedup paths, cap overflow, injection rendering, reminder extraction for both trigger kinds + due/matchable boundary logic, endpoint contracts incl. `event_trigger` round-trip, extraction-failure isolation.
- [x] Full suite passes.

## Manual Checks

- [x] Restart-survival demo beat works end-to-end through the real HTTP API across a stopped/restarted backend process.
- [x] Fact stated in session A is used in fresh session B's answer.
- [x] Duplicate fact statement does not duplicate the record.
- [x] "Remind me to…" appears in `GET /reminders` with the right `due_at`.
- [x] "When I leave tomorrow morning, remind me to take my water bottle" appears as an event reminder with resolved `valid_date`, window, and condition.
- [x] Legacy `{query}`-only requests unchanged.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
