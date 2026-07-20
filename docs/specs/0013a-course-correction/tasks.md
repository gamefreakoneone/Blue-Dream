# 0013a Course Correction Tasks

Phases run strictly in order A → D. **Do not commit or push at any point in this run** — leave all changes uncommitted in the working tree for on-device review; commits happen manually afterward. This is an explicit, documented deviation from the per-phase commit rule.

## Prerequisites

- [x] Baseline: `python -m pytest tests/` green (143 tests) in the `Project-Memoria` conda env; `cd UI && npm run build` clean; `git status` recorded in status.md as the starting point.

## Phase A — Backend: reminder intent, completion semantics, proactive field

- [x] `reminder_service.py`: restructure `mark_done` so daily time reminders roll `due_at` forward and stay `active` in both modes (`last_completed_at` set); patient one-shot/event still archive; delivery one-shot still → `done` (byte-identical). Add `archive()` + `archive_reminder` wrapper.
- [x] `api.py`: `POST /reminders/{reminder_id}/archive` (200 `{"ok": true}` / 404 / generic 500); add `"related_id"` to the `/proactive/pending` `public_fields` tuple; `query_jeeves` passes `session_id=request.session_id` into `run_single_query`.
- [x] `jeeves.py`: `reminder` intent in `QueryRoute` + additive router-prompt sentences per design; `_handle_reminder_query` with synchronous `ReminderExtraction` + `create_reminder(source="chat", origin_context=...)` + pure `_confirmation_text()` formatter + general-handler fallback on `is_reminder=false` + warm fixed failure text; `run_single_query` `session_id` kwarg + dispatch branch; `_handle_general_query` prompt gains "you can set reminders".
- [x] `profile_memory.py`: remove the reminder branch and `TurnMemoryExtraction`/`reminder_creator` plumbing; extraction keeps profile facts only.
- [x] Test hazards fixed in the same change: `tests/conftest.py` `canned_query` accepts the new kwarg; grep `tests/` for `TurnMemoryExtraction`/`reminder_creator` and rewrite `test_durable_memory.py` extraction cases (facts stored, no reminder created).
- [x] New/extended tests per design: `tests/test_reminder_intent.py`, reminder-service rollover/archive cases, API-contract archive + `related_id` + `/query`-shape cases.
- [x] Gate: full `python -m pytest tests/` green.

## Phase B — Backend: daily digest

- [x] `db_client.py`: `get_memory_digests_collection()` (optional unique index on `date`).
- [x] `Blue_dream_agents/memory_digest.py`: `DailyDigestService` per design — summaries + capped importance-sorted raw events per local day (events always gathered; skip empty days), sha256 source fingerprint, cache-by-date upsert, one structured synthesis call per uncached day (2–4 sentences, ≤3 highlights, `_limit_sentences` guard, patient-safe tone), per-day failure isolation (stale cache or omit), `asyncio.gather`, newest-first, JSON-safe.
- [x] `api.py`: `GET /memory/digest?days=&force=` with the generic-error pattern. `GET /memory/summaries` untouched.
- [x] `tests/test_memory_digest.py` per design.
- [x] Gate: full `python -m pytest tests/` green.

## Phase C — UI

- [x] `api.js`: `archiveReminder`, `digest`.
- [x] `RemindersScreen.jsx`: remove both create forms + form state; Done = busy-guard + reload (no optimistic removal — daily reminders roll forward and reappear under "Later"); Remove = optimistic archive via the new endpoint.
- [x] `ProactiveBubble.jsx`: "I'm okay" button on safety bubbles (`trigger_type === "safety" && related_id`) → `POST /alerts/{related_id}/ack {"action":"ok"}` → soft confirmation line; quiet retry on error; auto-ack of the proactive message unchanged.
- [x] `SafetyScreen.jsx`: 30s visible-poll + `visibilitychange` refetch (mount refetch already works via tab remount).
- [x] `App.jsx` + `icons.jsx`: top-bar new-chat icon button before the gear wired to `resetConversation`; DemoToolsSheet entry stays; visual check of two icon buttons.
- [x] `MemoriesScreen.jsx`: "Your days" → daily digest cards (Today/Yesterday/weekday labels, digest text, optional highlights, moments footer); facts section unchanged; fix room-by-room copy.
- [x] Gate: `npm run build` clean + manual browser smoke of all four tabs.

## Phase D — Docs + validation (no commits)

- [x] `TECHNICAL_DESIGN.md` Key Contracts: `POST /reminders/{id}/archive`, `GET /memory/digest` (spec 0013a rows); note `related_id` added to `/proactive/pending`; note the `reminder` router intent, the patient-done daily rollover, and the `memory_digests` cache collection.
- [x] `docs/FEATURE_STATUS.md`: 0013a row per the Update Rule (status, evidence, notes — including the explicit "validated, intentionally uncommitted" state).
- [x] This spec's `tasks.md` checkboxes + `status.md` evidence updated together.
- [x] `README.md` only if commands changed (none expected).
- [x] Final gates: full pytest green; `npm run build` clean; `git status` shows only uncommitted working-tree changes (zero new commits).

## Validation (record evidence in status.md)

- [x] Router smoke list (live or scripted): "where are my glasses" → object; "what was I doing yesterday" → time; "what did I mention about lunch" → semantic; "hello" → general; "remind me to take my pills at 3pm" → reminder; "did I take my medicine today" → NOT reminder.
- [x] `POST /query` with a reminder phrasing returns a confirming reply; `GET /reminders` shows the reminder with `source: "chat"` and the session id in `origin_context`.
- [x] `POST /reminders/{id}/done` on a daily reminder keeps it `active` with `due_at` rolled forward; on a one-shot archives it. `POST /reminders/{id}/archive` returns `{"ok": true}` then 404 on repeat.
- [x] `GET /proactive/pending` items include `related_id`; pending→delivered claim semantics unchanged.
- [x] `GET /memory/digest?days=7` returns newest-first digests; a second call serves from cache (zero LLM calls — assert via logs); a day without summaries still digests from raw events; `GET /memory/summaries` unchanged.
- [x] Browser: Reminders tab form-free with Done/Remove; safety bubble "I'm okay" clears the alert from Safety within one poll/visit; top-bar new-chat resets from any tab; Memories shows day-narrative cards.
- [x] Demo-morning warm-up noted in status.md: `curl http://localhost:8000/memory/digest?days=7` before recording.
- [ ] Pending human validation (phone, demo morning): reminder-intent round trip on the handset; safety ack flow end-to-end from a push notification; digest cards on the installed PWA.
