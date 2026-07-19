# 0006 Durable Memory Requirements

## Goal

Give the assistant memory that survives restarts and accumulates across sessions: MongoDB-backed conversation history with automatic summarization, a patient-profile fact store injected into every answer, and patient-created reminders. These map directly to the MemoryAgent track's "persistent memory that accumulates experience" and "remembers user preferences."

**Policy note:** this spec deliberately reverses the earlier project rule that conversation memory "must not be stored in MongoDB" (see `docs/archive/AGENTS-gemma-2026-07.md`). Durable conversation memory is now a designed product feature. Two boundaries remain: conversation memory is never embedded in ChromaDB, and it is never used as monitoring/safety evidence.

## Functional Requirements

### Conversation memory (`conversation_sessions` collection)

- Every `/query` with a `session_id` appends the user turn and the assistant reply to a Mongo session document: `{session_id, turns: [{role, text, ts}], summary, summary_updated_at, last_active_at, status}`.
- When stored turns exceed `CONVERSATION_MAX_TURNS` (default 12), the oldest overflow turns are summarized into `summary` by one LLM call and trimmed from `turns`.
- Context provided to the assistant = `summary` + recent turns — the same rendering contract `conversation_memory.py` provides today, so `jeeves.py`'s rewrite/general-chat behavior is unchanged.
- Context survives a backend restart mid-conversation (the demo beat).
- `POST /conversation/reset` marks the session `closed` (kept for the record, excluded from context); response contract unchanged.
- Clients without `session_id` behave exactly as today.

### Profile facts (`profile_facts` collection)

- After each `/query` chat turn, a structured extraction call mines the turn for stable personal facts; category ∈ `person | preference | routine | medical | safety`.
- New facts are deduplicated against existing active facts of the same category by one LLM comparison call (update/skip/add decision).
- Active facts (pinned first) are injected into synthesis and general-chat prompts as a "What you know about the patient" block.
- Endpoints: `GET /memory/profile`; `POST /memory/profile/{fact_id}/pin`; `POST /memory/profile/{fact_id}/archive`. Facts are archived, never deleted.
- A cap (`PROFILE_MAX_ACTIVE_FACTS`, default 50) guards prompt size; on overflow, lowest-confidence unpinned facts are archived first.

### Reminders (`reminders` collection)

Reminders come in two kinds, discriminated by `trigger_type`:

- **Time-triggered** (`trigger_type="time"`): "Remind me to take my pill at 8" fires when the wall clock reaches `due_at`.
- **Event-triggered** (`trigger_type="event"`): "When I leave for my morning walk tomorrow, remind me to take my water bottle" fires when a matching camera event is ingested (right room, right time window, matching observed behavior). Matching and delivery are spec 0008's job.

Document shape:

```
{reminder_id, text,
 trigger_type: "time" | "event",
 due_at,                        # time trigger only
 recurrence: none | daily,      # time trigger only
 event_trigger: {               # event trigger only, else null
   room_number: int | null,     # null = any room
   window_start: "HH:MM", window_end: "HH:MM",   # local-time window
   condition: str,              # natural-language behavior to match, e.g. "leaving for a walk (tying shoes, exiting)"
   valid_date: date | null      # "tomorrow" resolves to a date; null = every day until done/archived
 },
 status: active | done | archived, created_at, source: chat | api,
 origin_context: {session_id, created_from_text} | null   # audit trail; stored in Mongo only, never embedded in Chroma
}
```

- Both kinds are created from chat via structured extraction (extraction returns nothing for non-reminder turns; the extraction model distinguishes the two kinds and resolves relative phrases like "tomorrow morning when I leave" into `valid_date` + window + condition).
- Endpoints: `GET /reminders` (active, includes the discriminator), `POST /reminders` (create either kind), `POST /reminders/{id}/done`.
- Delivery is spec 0008's job; this spec only stores and lists them. Two query helpers are provided for 0008: `get_due_reminders(now)` (time-triggered, `due_at <= now`) and `get_matchable_event_reminders(now)` (event-triggered, active, `valid_date` today-or-null, local time inside the window).

## Technical Constraints

- All timestamps in the project timezone via `timezone_utils`.
- Extraction/dedup calls go through `llm/client.py` structured calls; extraction failures must never break the `/query` response (log and continue).
- Extraction runs after the response is produced (fire-and-forget task) so it adds no user-visible latency.
- Mongo indexes: `conversation_sessions.session_id` (unique), `profile_facts.status+category`, `reminders.status+due_at`, `reminders.status+trigger_type` (event-reminder pre-filter) — added to the shared index-setup path.

## Non-Requirements

- No cross-session identity/auth (single-patient system; all sessions belong to the patient).
- No fact extraction from camera events (stretch idea, out of scope).
- No reminder delivery UI (0008).

## Acceptance Criteria

- Mid-conversation backend restart: the follow-up question still resolves correctly from restored context.
- A fact stated in one session is used in an answer in a fresh session ("my daughter Sarah visits on Sundays" → next day, new session: "who is visiting this weekend?" names Sarah).
- Duplicate fact statements do not create duplicate records.
- "Remind me to…" creates a time reminder visible via `GET /reminders` with the right `due_at`; "when I leave tomorrow morning, remind me to…" creates an event reminder with a resolved `valid_date`, window, and condition.
- `/conversation/reset` and legacy no-session requests behave exactly as before.
- pytest covers: turn persistence + summarization trim, restart survival (new store instance reads same Mongo), fact extraction/dedup/injection (mocked LLM), reminder extraction (both trigger kinds), `get_due_reminders` / `get_matchable_event_reminders` window and date boundaries, endpoint contracts including `event_trigger` round-trip.
