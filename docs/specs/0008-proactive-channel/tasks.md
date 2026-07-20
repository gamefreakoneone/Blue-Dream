# 0008 Proactive Channel Tasks

## Prerequisites

- [x] Specs 0006 (reminders, conversation memory) and 0007 (summaries, pinned facts) completed.

## Implementation Tasks

- [x] Create `proactive_service.py`: message store, atomic `get_pending`, `acknowledge`, `check_due_reminders`, `maybe_morning_report`, `maybe_event_reminders`, dedupe guards, expiry.
- [x] Mongo indexes: `proactive_messages.status+created_at`, `related_id`.
- [x] Safety trigger in `alert_service` (patient-actionable alerts only; failure-isolated).
- [x] Morning-report trigger in the consolidator post-insert tail (LLM-composed, ≤3 sentences, dedupe per date).
- [x] Time-reminder delivery via poll-driven `check_due_reminders` + daily rollover.
- [x] Event-reminder matcher in the consolidator post-insert tail: `get_matchable_event_reminders` pre-filter → LLM condition match (`EVENT_REMINDER_LLM_MATCH` gate with deterministic fallback) → per-day dedupe → dated→done / undated→re-arm. Failure-isolated from ingestion. (Cut lever: droppable if the schedule slips; demo falls back to time reminders.)
- [x] `GET /proactive/pending` (+ session append) and `POST /proactive/{id}/ack` endpoints.
- [x] UI polling loop + "Memoria noticed" agent bubbles with image and action button + ack.
- [x] Document `PROACTIVE_EXPIRY_MINUTES`, `EVENT_REMINDER_LLM_MATCH` in `.env.example`.

## Tests

- [x] `tests/test_proactive.py`: all four trigger moments (safety, morning report, time reminders, event reminders), dedupe, expiry, delivery/ack transitions, atomic delivery, reminder rollover, event-reminder pre-filter/LLM-match/fallback/re-arm paths, morning-report first-event + timezone boundary, trigger failure isolation (alert path and ingestion path), endpoint contracts.
- [x] Full suite passes.

## Manual Checks

- [x] Hazard clip → warning bubble with highlighted image within one poll cycle.
- [x] Time reminder due → bubble; daily reminder reschedules.
- [x] Event reminder (water-bottle beat): matching leaving-the-room clip inside the window → bubble after processing; outside the window or a second same-day match → nothing.
- [x] Morning report fires once on the first event of a day.
- [x] Acked messages don't reappear across page reloads; expired messages never appear.

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.

## 2026-07-20 Room-Agnostic Safety Corrective Amendment

- [x] Generalize video observations and safety judgment to conservative environmental hazards in Bedroom and Living Room scenes.
- [x] Add backward-compatible `SafetyAssessment.hazard_object` and boundary-safe highlight-target precedence.
- [x] Preserve the severity threshold, patient alert/proactive failure isolation, Qwen→Gemini→original-image fallback, caretaker-only fall path, and geofence behavior.
- [x] Add `scripts/check_hazard_video.py` dry-run CLI with final-frame extraction, canonical staging, JSON evidence, and exit codes 0/1/2/3.
- [x] Add prompt, selector, image-builder, gate, and CLI regression tests.
- [x] Update README, technical design, feature ledger, and corrective-amendment evidence.
- [ ] User-supplied staged knife-on-bed video returns exit `0` and a visually correct knife highlight; intentionally pending until that media exists.
