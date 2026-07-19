# 0008 Proactive Channel Requirements

## Goal

Let the agent speak first. A trigger engine turns backend events into patient-facing messages that appear as agent-initiated chat turns in the web UI via polling — no push infrastructure. This unifies four product moments: hazard warnings ("please go back to the kitchen"), the morning report, due time reminders, and event-triggered reminders ("don't forget your water bottle" as the patient is seen leaving for their morning walk).

## Functional Requirements

### Message store

- New Mongo collection `proactive_messages`: `{message_id, trigger_type: "safety" | "morning_report" | "reminder", text, image_path (URL form, optional), action (optional: {label, url}), related_id (alert/reminder/summary id), status: "pending" | "delivered" | "acknowledged", created_at, delivered_at, expires_at}`. The generic `action` field stays in the schema for future triggers; no current trigger populates it.
- Messages expire (default `PROACTIVE_EXPIRY_MINUTES=60`): expired pending messages are never delivered (a stale "go back to the kitchen" is worse than silence).

### Triggers

1. **Safety**: when `alert_service` stores a patient-actionable alert (`target_role="patient"`, severity ≥ threshold), also create a proactive message from the alert's patient message + highlighted image.
2. **Morning report**: on the first ingested camera event of a calendar day (project timezone), compose a report from: yesterday's `memory_summaries` (or a fallback line if none), today's active reminders, and pinned safety facts. One LLM synthesis call renders it warm and short.
3. **Time reminders**: due reminders (from 0006's `get_due_reminders`) become proactive messages; `daily` reminders roll forward on delivery.
4. **Event-triggered reminders**: after each camera event is ingested, active event reminders (from 0006's `get_matchable_event_reminders`) are matched against it — Mongo pre-filter on room + local-time window + `valid_date`, then one structured LLM call judging whether the event description satisfies the reminder's `condition` (behind `EVENT_REMINDER_LLM_MATCH=true`; when disabled or on LLM failure, the room+window match alone fires — deterministic fallback). A match creates a `trigger_type="reminder"` proactive message; each reminder fires at most once per day (dedupe by `{reminder_id}_{local_date}`); dated reminders are marked `done` after firing, undated ones stay active and re-arm the next day. Known latency: the message lands after the recording ends and the video is processed (about a minute after the patient exits the frame) — same latency class as hazard alerts, acceptable for the leaving-the-house moment.

### Delivery (web chat polling)

- `GET /proactive/pending?session_id=...` returns pending unexpired messages (oldest first) and marks them `delivered`. The reminder-due check runs inside this endpoint (poll-driven — no background scheduler).
- `POST /proactive/{message_id}/ack` marks acknowledged.
- `UI/script.js` polls every `PROACTIVE_POLL_SECONDS` (default 5, client-side constant); each message renders as an agent chat bubble (distinct "Memoria noticed" styling), with the image and action button when present; rendering acks the message.
- Proactive turns are appended to the conversation session (as assistant turns) so follow-up questions like "what should I do?" have context.

## Technical Constraints

- Trigger failures must never break their host flows (alert storage, ingestion) — same isolation pattern as everywhere else.
- Morning-report first-event detection and event-reminder matching both live in the ingestion path (consolidator/ingest tail): each is an indexed Mongo query plus, for event reminders, at most one LLM call per pre-filtered candidate.
- All timestamps project-timezone; all image paths URL form.

## Non-Requirements

- No mobile push (post-hackathon backlog); the Expo app is untouched.
- No TTS auto-speak of proactive messages (0009 may add it as a stretch).
- No caregiver-facing proactive messages (caretaker alerts remain email/dashboard).
- No geofence check-in trigger: geofence proactive messages are post-hackathon backlog. The existing geofence endpoints remain in code as a preserved contract but gain no new behavior in this spec.
- Cut lever: if the schedule slips, event-triggered reminders ship schema-only (0006) and the matcher is dropped from this spec; the demo falls back to time reminders.

## Acceptance Criteria

- Kitchen-hazard demo: an ingested hazard event (safety alert stored) produces, within one poll cycle, an agent-initiated chat bubble with the warning text and highlighted image.
- Morning-report demo: the first event of a new day produces a report bubble citing yesterday's summary and today's reminders.
- Reminder demo: a due time reminder appears as a bubble; a daily reminder reschedules itself.
- Water-bottle demo: with an event reminder set for the living room morning window, ingesting a "person puts on shoes and leaves" clip inside the window produces the reminder bubble within one poll cycle; a same-room event outside the window fires nothing; a second matching event the same day fires nothing (dedupe).
- Expired messages are never delivered; acked messages never reappear; multiple browser sessions don't double-deliver (delivery is global, not per-session).
- pytest covers trigger creation for all four trigger moments (safety, morning report, time reminders, event reminders), expiry, delivered/acked transitions, poll-driven reminder generation, event-reminder pre-filter/LLM-match/dedupe/re-arm paths, and morning-report first-event detection.
