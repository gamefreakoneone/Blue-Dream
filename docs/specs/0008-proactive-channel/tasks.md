# 0008 Proactive Channel Tasks

## Prerequisites

- [ ] Specs 0006 (reminders, conversation memory) and 0007 (summaries, pinned facts) completed.

## Implementation Tasks

- [ ] Create `proactive_service.py`: message store, atomic `get_pending`, `acknowledge`, `check_due_reminders`, `maybe_morning_report`, `maybe_event_reminders`, dedupe guards, expiry.
- [ ] Mongo indexes: `proactive_messages.status+created_at`, `related_id`.
- [ ] Safety trigger in `alert_service` (patient-actionable alerts only; failure-isolated).
- [ ] Morning-report trigger in the consolidator post-insert tail (LLM-composed, ≤3 sentences, dedupe per date).
- [ ] Time-reminder delivery via poll-driven `check_due_reminders` + daily rollover.
- [ ] Event-reminder matcher in the consolidator post-insert tail: `get_matchable_event_reminders` pre-filter → LLM condition match (`EVENT_REMINDER_LLM_MATCH` gate with deterministic fallback) → per-day dedupe → dated→done / undated→re-arm. Failure-isolated from ingestion. (Cut lever: droppable if the schedule slips; demo falls back to time reminders.)
- [ ] `GET /proactive/pending` (+ session append) and `POST /proactive/{id}/ack` endpoints.
- [ ] UI polling loop + "Memoria noticed" agent bubbles with image and action button + ack.
- [ ] Document `PROACTIVE_EXPIRY_MINUTES`, `EVENT_REMINDER_LLM_MATCH` in `.env.example`.

## Tests

- [ ] `tests/test_proactive.py`: all four trigger moments (safety, morning report, time reminders, event reminders), dedupe, expiry, delivery/ack transitions, atomic delivery, reminder rollover, event-reminder pre-filter/LLM-match/fallback/re-arm paths, morning-report first-event + timezone boundary, trigger failure isolation (alert path and ingestion path), endpoint contracts.
- [ ] Full suite passes.

## Manual Checks

- [ ] Hazard clip → warning bubble with highlighted image within one poll cycle.
- [ ] Time reminder due → bubble; daily reminder reschedules.
- [ ] Event reminder (water-bottle beat): matching leaving-the-room clip inside the window → bubble after processing; outside the window or a second same-day match → nothing.
- [ ] Morning report fires once on the first event of a day.
- [ ] Acked messages don't reappear across page reloads; expired messages never appear.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
