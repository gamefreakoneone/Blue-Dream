# 0013a Course Correction Status

**Status: Implemented — automatic validation complete; pending demo-morning phone validation**

Implemented 2026-07-20 as the targeted correction to spec 0013. No spec 0009 work or unrelated 0013 surfaces were changed. Per this spec's explicit execution rule, the implementation is validated and intentionally left uncommitted for on-device review.

## Baseline and phase gates

- Starting `HEAD`: `20387f1600bf7ed1d87ed9047e16414cfa31eac1`.
- Starting working tree preserved: modified `docs/FEATURE_STATUS.md`; untracked `.agents/`, `docs/specs/0013a-course-correction/`, and `skills-lock.json`.
- Baseline: `conda run -n Project-Memoria python -m pytest tests/` → `143 passed, 2 warnings`.
- Baseline: `cd UI; npm run build` → clean Vite production build.
- Phase A gate: full suite → `149 passed, 2 warnings`.
- Phase B gate: full suite → `156 passed, 2 warnings`.
- Amendment gate: `tests/test_reminder_intent.py` → `6 passed`, including the no-time event-reminder default of `00:00`–`23:59`.
- Phase C gate: Vite production build clean; 30 modules transformed, JS 225.56 kB (69.82 kB gzip), CSS 20.36 kB (5.35 kB gzip).
- No dependencies, environment variables, setup commands, or prerequisites changed; `README.md` was intentionally left unchanged.

## Backend and contract evidence

- Reminder routing creates synchronously with `source: "chat"`, carries `session_id` and `created_from_text` in `origin_context`, and returns a deterministic local-time confirmation. Extraction failure returns the fixed warm response without exposing exception text.
- Event-reminder extraction uses `00:00`–`23:59` when no time constraint is supplied and keeps `06:00`–`11:00` only for explicitly morning-ish requests. Automated case: `when I leave the bedroom, remind me to pick up my bag`.
- Profile extraction is facts-only; `TurnMemoryExtraction` and reminder-creator plumbing were removed.
- Patient-mode daily completion sets `last_completed_at`, rolls `due_at` forward, and keeps the reminder active. Patient one-shot/event reminders archive; delivery-mode behavior remains covered.
- `POST /reminders/{id}/archive` returns `{"ok": true}` and returns 404 for an unknown or already inactive reminder.
- `/proactive/pending` includes additive `related_id`; tests preserve the atomic pending→delivered claim.
- `DailyDigestService` covers date-keyed indexing, newest-first concurrent processing, summary + active raw-event input, raw-event-only fallback, capped importance ordering/prompt budget, SHA-256 fingerprint cache, force/fingerprint regeneration, JSON-safe projection, stale-cache fallback, and per-day failure isolation.
- `GET /memory/summaries` was not changed. Preserved query/reset, alert, geofence, device, proactive, and static-mount contracts remain covered by the full suite.

## Isolated smoke evidence

### Router-only live-provider smoke

The six phrases were passed directly to `jeeves._route_query`; this layer performs no reminder, conversation, or Mongo writes.

| Phrase | Result |
|---|---|
| `where are my glasses` | `object` |
| `what was I doing yesterday` | `time` |
| `what did I mention about lunch` | `semantic` |
| `hello` | `general` |
| `remind me to take my pills at 3pm` | `reminder` |
| `did I take my medicine today` | `time` (not reminder) |

No live reminder or conversation records were created, so no production cleanup was required.

### Isolated ASGI/HTTPX smoke

Ran against disposable in-memory collections with a fake structured provider; production Mongo was never connected.

- `POST /query` returned a confirming reply; `GET /reminders` exposed `source: "chat"` and the dedicated session id in `origin_context`.
- Daily `POST /reminders/{id}/done` kept the reminder active and advanced it one day; one-shot completion archived.
- Archive returned 200/`{"ok": true}`, then 404 on repeat.
- Claimed proactive payload contained `related_id`.
- Digest response was newest-first (`2026-07-20`, `2026-07-19`); the first request made two structured calls, the second made zero additional calls and produced two `Daily digest cache hit` log entries.
- A day without summaries was generated from active raw events.
- The `/memory/summaries` response matched the canned pre-0013a payload exactly.
- Harness result: `production_mongo_writes: 0`.

## Rendered Chrome QA

The production `UI/dist` build was served with a disposable localhost mock API. Chrome exercised the default desktop viewport and a temporary 390×844 phone viewport; the override was reset and the QA tabs/server were closed afterward.

- Chat rendered the safety proactive bubble; **I'm okay** posted the linked alert acknowledgement and showed the soft confirmation.
- Reminders rendered as a list with zero forms. **Done** kept the daily reminder visible and moved it to **Later** with a **Tomorrow** due label; **Remove** archived and removed the event reminder.
- Safety showed **Everything looks settled** after the proactive acknowledgement.
- Memories preserved profile facts and rendered **Your story** cards with Today/Yesterday labels, highlights, and moment counts.
- The top-bar new-chat control reset the session from another tab and returned to Chat. The caregiver/demo-tools sheet entry remained available.
- The bottom navigation and both top-bar actions remained usable at 390×844; reminder actions and digest cards fit without horizontal overflow.
- Chrome console: zero errors and zero warnings.

## Follow-up phone finding: persistent safety acknowledgement

Phone testing found that the alert acknowledgement persisted in MongoDB, but the Chat bubble's thank-you state lived only inside `ProactiveBubble` and reset when Chat unmounted during tab navigation. The follow-up fix lifts `safety_acknowledged` onto the App-owned proactive message; the bubble now keeps only its transient request-busy state. This preserves **Thank you — noted that you're okay** when navigating away from Chat and back, without changing any backend contract.

- `node --test tests/messageState.test.mjs` from `UI/` → `2 passed` (immutable App-message update plus repeat/unknown-id stability).
- Follow-up `UI/npm run build` → clean Vite 8.1.5 build; 31 modules transformed, JS 225.82 kB (69.89 kB gzip), CSS 20.36 kB (5.35 kB gzip).

## Final gate

- Post-documentation `conda run -n Project-Memoria python -m pytest tests/` → `157 passed, 2 warnings in 27.90s` on the final rerun (all 143 baseline tests plus 14 new tests).
- Final `UI/npm run build` → clean Vite 8.1.5 build after the persistent-ack follow-up; 31 modules transformed, JS 225.82 kB (69.89 kB gzip), CSS 20.36 kB (5.35 kB gzip).
- `git diff --check` reported no whitespace errors (Git emitted only the repository's existing Windows LF→CRLF and inaccessible global-ignore warnings).
- Final `HEAD`: `20387f1600bf7ed1d87ed9047e16414cfa31eac1`, unchanged from baseline. Zero commits and zero pushes were created.
- Final `git status --short` contains only uncommitted working-tree changes: the preserved starting entries plus the scoped 0013a backend, UI, test, and documentation files. No temporary QA server or smoke harness file is inside the repository.

## Demo-morning warm-up

Before recording, warm the seven-day digest cache:

```powershell
curl http://localhost:8000/memory/digest?days=7
```

## Pending human validation

- [ ] Reminder-intent round trip on the handset.
- [ ] Safety acknowledgement from a push notification.
- [ ] Digest cards in the installed PWA.
