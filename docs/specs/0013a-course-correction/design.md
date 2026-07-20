# 0013a Course Correction Design

> Contracts you must not break: `POST /query` request/response shape, `POST /conversation/reset`, all alert endpoints, all geofence endpoints, `/proactive/*` semantics (atomic pending→delivered claim — the only change is the additive `related_id` field in the pending payload), `POST /devices/register`, `/storage` + `/capture` mounts, `GET /memory/summaries` (spec 0012 depends on it byte-for-byte). Delivery-mode `mark_done` behavior must stay byte-identical (the proactive sweep depends on it).

## Item 1 — Reminder intent in the Jeeves router

### `Blue_dream_agents/jeeves.py`

- `QueryRoute.intent` (line ~60): `Literal["object", "time", "semantic", "general", "reminder"]`.
- `_route_query` (line ~215) system prompt: **additive-only** change, keeping the four existing intent descriptions verbatim. Append:
  - `"Choose 'reminder' only when the user explicitly asks to be reminded or to set, create, or schedule a reminder, such as 'remind me to take my pills at 3pm'."`
  - In the structured-output instruction: `"Questions about whether something already happened are never 'reminder'."`
  The deterministic pre-route (`_deterministic_route`) is untouched and still runs first.
- New handler:

  ```python
  async def _handle_reminder_query(query: str, *, session_id: Optional[str] = None) -> JeevesResponse:
  ```

  Flow:
  1. `invoke_structured` with `output_model=ReminderExtraction` (import from `reminder_service`), router model, `max_tokens=500`. Prompt payload: `{"now": now.isoformat(), "timezone": str(now.tzinfo), "user_message": query}`. Reuse the extraction wording that already works in `profile_memory.py` (~lines 156-170): resolve relative times in the project timezone; explicitly morning-ish event window = 06:00–11:00; **event reminders with no stated time constraint use the full-day window 00:00–23:59** (the matcher requires a window and skips events outside it — a fabricated narrow window silently drops the reminder); time reminders require `due_at`; event reminders require condition/window and take optional room and `valid_date`.
  2. `not extraction.is_reminder` → fall through to `_handle_general_query(query, ...)`; tag `data["route_intent"] = "reminder"`, `data["reminder_fallback"] = True`.
  3. Else build `ReminderCreate(...)` and `create_reminder(reminder, source="chat", origin_context={"session_id": session_id, "created_from_text": query})`.
  4. Confirmation text via a **pure function `_confirmation_text(extraction) -> str`** (extracted for unit testing, no LLM call):
     - time: `"Of course. I'll remind you to {text} {today|tomorrow|Weekday, Mon D} at {h:MM AM}."` + `" I'll repeat it every day."` when `recurrence == "daily"` (port the UI's `dueLabel` phrasing to Python).
     - event: `"Of course. I'll remind you to {text} when I notice {condition}."`
  5. Return `JeevesResponse(response_type="general", text=confirmation, data={"route_intent": "reminder", "reminder": <json-safe created doc>})`.
  6. Wrap extraction + creation in try/except → warm fixed text on failure ("I had a little trouble saving that reminder just now. Could you ask me again in a moment?"); the outer `run_single_query` catch backstops.
- `run_single_query` (line ~511): additive optional kwarg `session_id: Optional[str] = None`; dispatch branch for `route.intent == "reminder"` among the existing elifs, merging `route_reason` + conversation data into `response.data` like the other branches.
- `_handle_general_query` (line ~475) system prompt: append `"You can set reminders for the patient; never claim you cannot set reminders."`

### `Blue_dream_agents/api.py`

- `query_jeeves` (line ~294): `run_single_query(request.query, conversation_context=conversation_context, session_id=request.session_id)`. Response shape unchanged.

### `Blue_dream_agents/profile_memory.py` — clean removal of the reminder branch

- Delete the `if extraction.reminder.is_reminder:` block (~lines 174-192).
- `extract_and_store` switches `output_model` to `ProfileFactExtraction`; drop the reminder sentences from its prompts; reduce `max_tokens` (~600).
- Delete `TurnMemoryExtraction`, the `reminder_creator` ctor param, the `ReminderCreator` alias, and the now-unused `reminder_service` imports. `ReminderExtraction` stays in `reminder_service.py`, now consumed by jeeves.

### Known test hazards (fix in the same change)

- `tests/conftest.py` stubs `run_single_query` as `canned_query(query, conversation_context=None)` — it must accept the new kwarg (`**kwargs` or explicit `session_id=None`) or every API-contract test breaks.
- Grep `tests/` for `TurnMemoryExtraction` and `reminder_creator` before deleting; rewrite the `tests/test_durable_memory.py` extraction cases (~lines 253-349) to assert facts are still stored and **no** reminder is created.

## Item 2 — Reminders: completion semantics + archive

### `Blue_dream_agents/reminder_service.py`

- `mark_done` (~lines 239-289) restructure — roll daily time reminders forward in **both** modes:

  ```python
  is_recurring_time = (
      document.get("trigger_type") == "time"
      and document.get("recurrence") == "daily"
      and isinstance(document.get("due_at"), dt.datetime)
  )
  if is_recurring_time:   # existing delivery rollover logic; stays active; set last_completed_at
  elif mode == "patient": # archive (existing one-shot/event behavior)
  else:                   # delivery one-shot -> status "done" (byte-identical)
  ```

- New `async def archive(self, reminder_id, *, now=None) -> bool` + module wrapper `archive_reminder`: `update_one({"reminder_id": id, "status": "active"}, {"$set": {"status": "archived", "archived_at": ts, "updated_at": ts}})`, truthy on `matched_count`.

### `Blue_dream_agents/api.py`

- `POST /reminders/{reminder_id}/archive` after `complete_reminder` (~line 453): 200 `{"ok": true}` / 404 / generic 500 — mirrors the `POST /memory/profile/{fact_id}/archive` precedent (honest never-erase verb; the UI says "Remove").

## Item 3 — Safety ack sync

- `api.py` `get_proactive_messages` (~line 489): add `"related_id"` to the `public_fields` tuple. Only safety messages carry an alert id; reminder/morning `related_id`s are synthetic dedupe keys — the UI must gate on `trigger_type === "safety"`.
- `UI/src/components/ProactiveBubble.jsx`: local `ackState` (`idle|busy|done`). When `trigger_type === "safety" && related_id && ackState !== "done"`, render an "I'm okay" primary button below the image → `api.acknowledgeAlert(message.related_id, "ok")` → `done` shows a soft line ("Thank you — noted that you're okay."); error returns to `idle` (quiet retry, no scary text). The ChatScreen render-time auto-ack of the proactive message stays untouched.
- `UI/src/screens/SafetyScreen.jsx`: tab switches already remount screens (App renders a different component type per route), so the mount refetch works today. Add one effect: 30-second interval calling `load()` when `!document.hidden`, plus a `visibilitychange` listener; both cleaned up on unmount.

## Item 4 — Top-bar new-chat button

- `UI/src/App.jsx` (~line 65): inside `<header className="topbar">`, before the gear: `<button className="icon-button" type="button" onClick={resetConversation} aria-label="Start a new conversation"><Icon name="newchat" size={25} /></button>`.
- `UI/src/icons.jsx`: add a `newchat` glyph (speech bubble + plus, same 24-viewBox stroke style); reusing `plus` is the acceptable fallback. Quick visual check that the flex topbar accommodates two icon buttons.
- DemoToolsSheet "Start fresh conversation" stays.

## Item 5 — Daily digest

### New module `Blue_dream_agents/memory_digest.py`

Injectable-service pattern (as `ReminderService`):

```python
class DailyDigestText(BaseModel):
    text: str = Field(min_length=1)
    highlights: list[str] = Field(default_factory=list)

class DailyDigestService:
    def __init__(self, *, events_collection=None, summaries_collection=None, digests_collection=None): ...
    async def get_digests(self, days: int = 7, *, now=None, force: bool = False) -> list[dict]
    async def _digest_for_day(self, day: dt.date, *, force: bool) -> Optional[dict]
    async def _gather_sources(self, day: dt.date) -> tuple[list[dict], list[dict]]

async def get_daily_digests(days: int = 7, *, force: bool = False) -> list[dict]  # module wrapper
```

Per-day logic, for each local day from today back `days - 1`:

1. Summaries: `memory_summaries.find({"date": day.isoformat()})` sorted by room.
2. Events (**always gathered** — covers days consolidation hasn't reached and partially consolidated days): active events in the local-day window, converted via `memory_event_from_mongo` (tz-safe), importance-desc then timestamp-asc, **cap ~12**, budgeted with the same `prompt_budget` tooling as `memory_lifecycle._summary_prompt_records` (~8k chars), fields `timestamp`, `room_name`, `memory=semantic_text`.
3. Both empty → skip the day (no card).
4. Fingerprint: `sha256("|".join(sorted(summary_ids) + sorted(event_ids)))`.
5. Cache: `memory_digests.find_one({"date": ...})`; hit + fingerprint match + not `force` → return cached (zero LLM calls).
6. Else one `invoke_structured` call (synthesis model, `max_tokens=400`, `with_patient_answer_context`): warm, first/second person, **2–4 short sentences**, ≤3 short highlights, only supplied material, never mention cameras/monitoring/databases, never invent. Defensive `_limit_sentences(text, 4)` (mirror `proactive_service._limit_to_three_sentences`).
7. Upsert by date:

   ```
   { digest_id: "dig_<date>", date: "YYYY-MM-DD", text, highlights: [str],
     source_fingerprint, source_summary_count, source_event_count,
     created_at ($setOnInsert), updated_at }
   ```

8. Failure isolation: per-day try/except → stale cached digest if present, else omit the day. Never a wholesale 500 for one bad day.
9. `get_digests`: days via `asyncio.gather(..., return_exceptions=True)` (cold 7-day load ≈ one LLM-call latency, not seven sequential), newest-first, `_json_safe` serialization (drop `_id`).

### `Blue_dream_agents/db_client.py`

- `get_memory_digests_collection()` → `db["memory_digests"]` (copy the adjacent getter pattern). Optional unique index on `date`; the upsert keeps it safe regardless.

### `Blue_dream_agents/api.py`

```python
@app.get("/memory/digest")
async def get_memory_digest(days: int = Query(default=7, ge=1, le=31), force: bool = Query(default=False)):
    # {"digests": [...]} — generic-error pattern on failure
```

`GET /memory/summaries` untouched.

### UI

- `UI/src/api.js`: `archiveReminder(reminderId)` → `POST /reminders/{id}/archive`; `digest(days = 7)` → `GET /memory/digest?days=`. `createReminder` stays (curl/demo parity).
- `UI/src/screens/RemindersScreen.jsx`: delete both forms and all form state/handlers (`defaultDue`, `create`, `createEventReminder`, associated `useState`s). `complete()`: **no optimistic filter-out** (wrong for daily rollover) — `busyId` guard, `await api.completeReminder(id)`, then `await load()`; daily reminders reappear under "Later" via existing `isToday`/`dueLabel`. New `remove(id)`: optimistic filter-out + `api.archiveReminder(id)`; on error, show the friendly error and `load()`. Card actions: Done (primary) + Remove (`.hide-button` style, existing `close` icon).
- `UI/src/screens/MemoriesScreen.jsx`: replace the summaries effect with `api.digest(7)`; one card per digest reusing `summary-card`/`summary-date` CSS: day label (Today / Yesterday / `toLocaleDateString` weekday+date — parse as `new Date(`${iso}T12:00:00`)` to dodge UTC off-by-one), digest text, optional highlights `<ul>` (skip when empty), footer `"{source_event_count + source_summary_count} moments remembered"`. Section copy: "One gentle note about each recent day." Facts section unchanged.

## Test plan (mocked LLM throughout; follow `monkeypatch.setattr(module, "invoke_structured", stub)` idioms in `tests/test_durable_memory.py`)

1. `tests/test_reminder_intent.py` (new): reminder route dispatch → creation with `source="chat"` + `origin_context.session_id`; confirmation text contains reminder text + due phrase; `data.route_intent == "reminder"`; `is_reminder=False` → general fallback, nothing created; creation raises → warm text, no 500; `_confirmation_text` unit cases (time / daily / event); a no-time event reminder ("when I leave the bedroom, remind me to pick up my bag") asserting the full-day 00:00–23:59 window in the created document.
2. `tests/test_durable_memory.py` (update): extraction stores facts, creates no reminders; remove `reminder_creator` injections.
3. Reminder service (extend where `mark_done` is covered): patient mode on daily → stays `active`, `due_at` +1 day, `last_completed_at` set; patient one-shot → `archived` (regression); delivery mode byte-identical (regression); `archive()` → `archived`, unknown/inactive → falsy.
4. `tests/test_api_contract.py` (extend): `POST /reminders/{id}/archive` 200 + 404; `GET /proactive/pending` payload includes `related_id` (and still `trigger_type`); `POST /query` shape unchanged with the widened conftest stub.
5. `tests/test_memory_digest.py` (new, fake async collections injected): cache hit + fingerprint match → zero LLM calls; no summaries + events present → prompt payload carries event moments (fallback proof); fingerprint change or `force` → regenerate + upsert; LLM failure with stale cache → stale returned; failure with no cache → day omitted, no exception; endpoint newest-first + JSON-safe; `GET /memory/summaries` unchanged.

## Risk register

1. **Router regression on the four existing intents** (highest risk): additive prompt wording only; deterministic pre-route untouched; mocked dispatch tests; manual smoke list in tasks.md.
2. `run_single_query` signature vs the conftest stub — fixed in the same change.
3. `extract_and_store` refactor rippling into tests referencing deleted symbols — grep first.
4. Digest cold-load latency/LLM cost — cache + gather + event cap + a pre-demo warm-up call.
5. Daily-Done UX — reload from the server instead of optimistic removal so rolled-forward reminders reappear.
