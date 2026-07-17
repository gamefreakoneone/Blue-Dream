# 0008 Proactive Channel Requirements

## Goal

Let the agent speak first. A trigger engine turns backend events into patient-facing messages that appear as agent-initiated chat turns in the web UI via polling — no push infrastructure. This unifies four product moments: hazard warnings ("please go back to the kitchen"), geofence check-ins with a route home, the morning report, and due reminders.

## Functional Requirements

### Message store

- New Mongo collection `proactive_messages`: `{message_id, trigger_type: "safety" | "geofence" | "morning_report" | "reminder", text, image_path (URL form, optional), action (optional: {label, url}), related_id (alert/reminder/summary id), status: "pending" | "delivered" | "acknowledged", created_at, delivered_at, expires_at}`.
- Messages expire (default `PROACTIVE_EXPIRY_MINUTES=60`): expired pending messages are never delivered (a stale "go back to the kitchen" is worse than silence).

### Triggers

1. **Safety**: when `alert_service` stores a patient-actionable alert (`target_role="patient"`, severity ≥ threshold), also create a proactive message from the alert's patient message + highlighted image.
2. **Geofence exit**: when `POST /geofence/events` records an `exit`, create a check-in message ("I noticed you've left home. Is everything okay?") with a Google Maps directions link to the configured home coordinates as the `action`.
3. **Morning report**: on the first ingested camera event of a calendar day (project timezone), compose a report from: yesterday's `memory_summaries` (or a fallback line if none), today's active reminders, and pinned safety facts. One LLM synthesis call renders it warm and short.
4. **Reminders**: due reminders (from 0006's `get_due_reminders`) become proactive messages; `daily` reminders roll forward on delivery.

### Delivery (web chat polling)

- `GET /proactive/pending?session_id=...` returns pending unexpired messages (oldest first) and marks them `delivered`. The reminder-due check runs inside this endpoint (poll-driven — no background scheduler).
- `POST /proactive/{message_id}/ack` marks acknowledged.
- `UI/script.js` polls every `PROACTIVE_POLL_SECONDS` (default 5, client-side constant); each message renders as an agent chat bubble (distinct "Memoria noticed" styling), with the image and action button when present; rendering acks the message.
- Proactive turns are appended to the conversation session (as assistant turns) so follow-up questions like "what should I do?" have context.

## Technical Constraints

- Trigger failures must never break their host flows (alert storage, geofence event handling, ingestion) — same isolation pattern as everywhere else.
- Morning-report first-event detection lives in the ingestion path (consolidator/ingest tail): "is this the first event of today?" — one indexed Mongo query.
- All timestamps project-timezone; all image paths URL form.

## Non-Requirements

- No mobile push (post-hackathon backlog); the Expo app is untouched.
- No TTS auto-speak of proactive messages (0009 may add it as a stretch).
- No caregiver-facing proactive messages (caretaker alerts remain email/dashboard).

## Acceptance Criteria

- Kitchen-hazard demo: an ingested hazard event (safety alert stored) produces, within one poll cycle, an agent-initiated chat bubble with the warning text and highlighted image.
- Geofence demo: the UI "Simulate safe-zone exit" button produces a check-in bubble with a working Google Maps action link.
- Morning-report demo: the first event of a new day produces a report bubble citing yesterday's summary and today's reminders.
- Reminder demo: a due reminder appears as a bubble; a daily reminder reschedules itself.
- Expired messages are never delivered; acked messages never reappear; multiple browser sessions don't double-deliver (delivery is global, not per-session).
- pytest covers trigger creation for all four types, expiry, delivered/acked transitions, poll-driven reminder generation, and morning-report first-event detection.
