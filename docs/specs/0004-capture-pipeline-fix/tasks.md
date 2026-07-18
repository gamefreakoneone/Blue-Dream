# 0004 Capture Pipeline Fix Tasks

## Prerequisites

- [x] Specs 0001–0003 implementation/offline gates completed. Spec 0002's provider-backed live checks remain explicitly assigned to spec 0005.
- [x] One physical camera available for the live checks; the two-camera resolution check uses the documented single-camera fallback.

## Implementation Tasks

- [x] Introduce `CameraRig` dataclass replacing the parallel per-camera dicts.
- [x] Extract `load_capture_config`, `init_cameras`, `summarize_detections`, `update_recording_state`, `handle_fall_state`, `draw_hud`; hoist per-frame logic out of the `for result in results:` loop.
- [x] Weights path from module location with `FALL_MODEL_PATH` override.
- [x] `CAMERA_INDICES` / `CAMERA_ROOM_MAP` env parsing with current values as defaults; document in `.env.example`.
- [x] Per-camera VideoWriter dimensions from each rig.
- [x] Fix misleading buffer comments.
- [x] Add `alert_type` + `target_role` to alert documents (defaults `hazard`/`patient` for existing paths); filter `GET /alerts/patient` to `target_role="patient"`.
- [x] Add caretaker email channel to `alert_service` (Gmail send via executor when configured; honest `delivery_status` otherwise).
- [x] Add `create_alert_sync` bridge using the queue thread's event loop; wire confirmed falls to it; remove GmailAgent from `camera_feed.py`.
- [ ] (Optional, intentionally skipped) Copy `audio_capture` frames under lock in `stop_recording`; not required for this spec's gate.

## Tests

- [x] `tests/test_capture_state.py`: start/continue/stop transitions, 3.5s fall confirmation single-fire, empty-detections regression, room-map parsing, per-rig dimensions, idle loop responsiveness, and exact queue payload.
- [x] Full suite passes: 68 tests.

## Manual Checks

- [x] Run capture from a non-repo-root CWD: model loaded from the module path and outputs landed under project `Storage/`.
- [x] Walk-in/walk-out produced a playable recording; the exact stored-path queue → consolidator payload is verified offline. Provider-backed understanding/Mongo ingestion remains the spec 0005 live gate.
- [x] Single available camera produced a playable 1920x1080 MP4; mixed-resolution hardware was unavailable and is noted in `status.md`.
- [x] Simulated fall → caretaker-targeted `safety_alerts` record with honest `not_configured` status at capture time; configured Gmail delivery is executor-tested; live `GET /alerts/patient` excluded the fall.

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence.
- [ ] Commit and record the implementation SHA in the evidence follow-up.
