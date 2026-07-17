# 0008 Proactive Channel Tasks

## Prerequisites

- [ ] Specs 0006 (reminders, conversation memory) and 0007 (summaries, pinned facts) completed.

## Implementation Tasks

- [ ] Create `proactive_service.py`: message store, atomic `get_pending`, `acknowledge`, `check_due_reminders`, `maybe_morning_report`, dedupe guards, expiry.
- [ ] Mongo indexes: `proactive_messages.status+created_at`, `related_id`.
- [ ] Safety trigger in `alert_service` (patient-actionable alerts only; failure-isolated).
- [ ] Geofence-exit trigger with Google Maps action (skip action when home unconfigured).
- [ ] Morning-report trigger in the consolidator post-insert tail (LLM-composed, ≤3 sentences, dedupe per date).
- [ ] Reminder delivery via poll-driven `check_due_reminders` + daily rollover.
- [ ] `GET /proactive/pending` (+ session append) and `POST /proactive/{id}/ack` endpoints.
- [ ] UI polling loop + "Memoria noticed" agent bubbles with image and action button + ack.
- [ ] Document `PROACTIVE_EXPIRY_MINUTES` in `.env.example`.

## Tests

- [ ] `tests/test_proactive.py`: all four trigger types, dedupe, expiry, delivery/ack transitions, atomic delivery, reminder rollover, morning-report first-event + timezone boundary, trigger failure isolation, endpoint contracts.
- [ ] Full suite passes.

## Manual Checks

- [ ] Hazard clip → warning bubble with highlighted image within one poll cycle.
- [ ] "Simulate safe-zone exit" → check-in bubble; maps link opens correct directions.
- [ ] Reminder due → bubble; daily reminder reschedules.
- [ ] Morning report fires once on the first event of a day.
- [ ] Acked messages don't reappear across page reloads; expired messages never appear.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
