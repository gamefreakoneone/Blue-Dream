# 0008 Proactive Channel Design

## Contracts You Must Not Break

- Alert storage and ingestion must succeed even when proactive-message creation fails (try/except-log around every trigger call).
- Existing geofence endpoints are a preserved contract but gain no new behavior (geofence proactive check-ins are post-hackathon backlog).
- `/query` and conversation-session contracts unchanged; proactive turns append via the existing `conversation_memory.append_conversation_turn` API.
- Patient-facing text rules: warm, short, no raw internals.
- The YOLO fall path remains caretaker-only; geofence behavior remains unchanged.

## 2026-07-20 room-agnostic safety corrective amendment

- `video_agent.py` changes only its observation policy: clear environmental hazards in any configured room set `danger_candidate` and name the concrete object/state; ordinary object presence and safe use do not.
- `SafetyAssessment` adds optional `hazard_object` with an empty default. The judge returns a concise visible label for actionable warnings and explicitly excludes fall/geofence decisions.
- `alert_service.choose_highlight_target` selects: normalized structured target → one unambiguous whole-word room-object match → whole-word legacy alias → no target/original image. Alias evidence may disambiguate a contextual surface such as `bed` from the actual `knife`; raw substring matching is removed.
- Spatial grounding combines the detailed explanation, factual observed hazards, and final scene state. Existing Qwen/Gemini fallback, media-path forms, highlight statuses, severity gate, persistence order, proactive failure isolation, and push behavior are unchanged.

Dry-run CLI:

```powershell
conda run -n Project-Memoria python scripts/check_hazard_video.py --video "C:\path\knife-demo.mp4" --room bedroom [--screenshot "C:\path\final.jpg"]
```

The script stages external media under `Storage/hazard_checks/<run-id>/`, extracts the production-style final frame when needed, and writes `result.json`. Exit codes: `0` alert+highlight, `1` runtime/configuration failure, `2` no actionable alert, `3` alert+original-image fallback. It never invokes alert creation or any persistence/delivery function.

## Module: `Blue_dream_agents/proactive_service.py`

```python
async def create_message(*, trigger_type, text, image_path=None, action=None,
                         related_id=None, expires_minutes=None) -> str   # message_id
async def get_pending(now) -> list[dict]   # pending, unexpired, oldest first; marks delivered
async def acknowledge(message_id) -> bool
async def check_due_reminders(now) -> None # creates time-reminder messages; rolls daily reminders
async def maybe_morning_report(event_timestamp) -> None  # first-event-of-day detection + report
async def maybe_event_reminders(event) -> None  # event-reminder matching against a just-ingested event
```

- `message_id = f"pm_{uuid4().hex[:12]}"`. Dedupe guards: one morning report per date (`related_id = f"morning_{date}"`, skip if exists); one message per alert id; one per time reminder per due-time; one per event reminder per local date (`related_id = f"{reminder_id}_{local_date}"`).
- `get_pending` marks delivered atomically (`find_one_and_update` loop) so two overlapping polls can't double-deliver.
- Mongo indexes: `status + created_at`, `related_id`.

## Trigger wiring

1. **Safety** — in `alert_service`, after a patient-actionable alert document is stored (the existing severity gate already applied): `create_message(trigger_type="safety", text=alert.body or patient_message, image_path=alert.image_path, related_id=alert_id)`.
2. **Morning report** — in the consolidator's post-insert tail (and the 0010 `/ingest` tail): `await maybe_morning_report(event.timestamp)`. Detection: count today's events ≤ 1 → first event. Compose via one `invoke_structured`/text call from: yesterday's `memory_summaries` texts (fallback: "a quiet day yesterday"), today's active reminders, pinned safety profile facts. Keep it ≤3 sentences, warm tone (reuse `prompt_context` patient-facing prefix).
3. **Time reminders** — `check_due_reminders` runs at the top of the `/proactive/pending` handler: for each due reminder create a message (`related_id=f"{reminder_id}_{due_at.isoformat()}"` for dedupe), then `mark_done` or roll `daily` forward.
4. **Event reminders** — in the consolidator's post-insert tail, right beside `maybe_morning_report` (same isolation: try/except-log, never blocks ingestion): `await maybe_event_reminders(event)`. Flow: `reminder_service.get_matchable_event_reminders(event.timestamp)` (Mongo pre-filter: active event reminders, room match or reminder room null, event local time inside window, `valid_date` today-or-null) → per candidate, one structured LLM call (`class EventReminderMatch(BaseModel): matches: bool; reason: str`) judging the event's `semantic_text` against the reminder's `condition`, gated by `EVENT_REMINDER_LLM_MATCH` (default true; when false or on LLM failure the pre-filter match alone fires — deterministic fallback, never a silent drop) → on match `create_message(trigger_type="reminder", text=reminder.text, related_id=f"{reminder_id}_{local_date}")` → dated reminders (`valid_date` set) are marked `done`; undated ones stay `active` and the date-scoped `related_id` prevents re-firing until the next day. Latency caveat (document in README/demo notes): the bubble lands after recording end + video processing, ~a minute after the patient exits the frame.

## API (`api.py`)

```
GET  /proactive/pending?session_id=...  -> {"messages": [{message_id, trigger_type, text, image_path, action, created_at}]}
POST /proactive/{message_id}/ack        -> {"ok": true}
```

The pending handler: `check_due_reminders(now)` → `get_pending(now)` → for each returned message, `conversation_memory.append_conversation_turn(session_id, "assistant", text)` when a session_id is supplied (so follow-ups have context) → return. JSON-safe serialization.

## UI (`UI/script.js`, `UI/styles.css`)

- `setInterval(pollProactive, 5000)` started after DOM load; skipped while a poll is in flight.
- Each message renders as an agent bubble with a small "Memoria noticed" label, optional image (`image_path` used directly — 0002 contract), and optional action button opening `action.url` in a new tab; then `POST .../ack`.
- A gentle notification sound or visual pulse is optional polish, not required.

## Env

`PROACTIVE_EXPIRY_MINUTES=60`, `EVENT_REMINDER_LLM_MATCH=true` (server), poll interval as a JS constant. Document in `.env.example`.

## Tests (`tests/test_proactive.py`)

- Creation + dedupe per trigger type (mocked LLM for morning report and event-reminder matching).
- Expiry: expired pending never returned; delivered/acknowledged transitions; atomic delivery (two concurrent get_pending calls split, don't duplicate — simulate with the fake collection).
- Poll-driven time reminders: due → message + daily rollover; not-due → nothing.
- Event reminders: pre-filter boundaries (room, window edges, valid_date today/other/null), LLM-match true/false, `EVENT_REMINDER_LLM_MATCH=false` and LLM-failure fallback paths, per-day dedupe, dated→done vs undated→re-arm, matcher raising doesn't break ingestion (isolation regression).
- Morning report: first event of day fires once; second event same day doesn't; date boundary respects project timezone.
- Trigger failure isolation: proactive creation raising doesn't break alert storage (regression test around the alert path).
- Endpoint contract tests.
- Corrective-amendment tests: structured target precedence; unambiguous room-object and alias fallbacks; false-substring regressions; safe knife use vs knife-left-on-bed prompt policy; fall/geofence patient-gate exclusion; image generation/fallback; all CLI exit states and no-persistence dry-run behavior.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live demo-beat rehearsal: first run the dry-run CLI on a staged knife-on-bed clip and require exit `0` plus a visually correct knife box. Then ingest the clip through capture → warning bubble with image inside ~5s of the alert; create a reminder due in one minute → bubble arrives; set an event reminder ("water bottle when I leave this morning") → ingest a matching leaving-the-room clip inside the window → reminder bubble after processing, and a second matching clip fires nothing; morning report fires on the first event after midnight (or temporarily set the date window to test).
