# 0004 Capture Pipeline Fix Tasks

## Prerequisites

- [ ] Specs 0001–0003 completed.
- [ ] Physical cameras available for the live checks (or recorded test clips).

## Implementation Tasks

- [ ] Introduce `CameraRig` dataclass replacing the parallel per-camera dicts.
- [ ] Extract `load_capture_config`, `init_cameras`, `summarize_detections`, `update_recording_state`, `handle_fall_state`, `draw_hud`; hoist per-frame logic out of the `for result in results:` loop.
- [ ] Weights path from module location with `FALL_MODEL_PATH` override.
- [ ] `CAMERA_INDICES` / `CAMERA_ROOM_MAP` env parsing with current values as defaults; document in `.env.example`.
- [ ] Per-camera VideoWriter dimensions from each rig.
- [ ] Fix misleading buffer comments.
- [ ] Add `alert_type` + `target_role` to alert documents (defaults `hazard`/`patient` for existing paths); filter `GET /alerts/patient` to `target_role="patient"`.
- [ ] Add caretaker email channel to `alert_service` (Gmail send via executor when configured; honest `delivery_status` otherwise).
- [ ] Add `create_alert_sync` bridge using the queue thread's event loop; wire confirmed falls to it; remove GmailAgent from `camera_feed.py`.
- [ ] (Optional) Copy `audio_capture` frames under lock in `stop_recording`.

## Tests

- [ ] `tests/test_capture_state.py`: start/continue/stop transitions, 3.5s fall confirmation single-fire, empty-detections regression, room-map parsing.
- [ ] Full suite passes.

## Manual Checks

- [ ] Run capture from a non-repo-root CWD: model loads, outputs land under project `Storage/`.
- [ ] Walk-in/walk-out produces a recording that reaches Mongo through the queue.
- [ ] Two different-resolution cameras both produce playable MP4s (or verify single-camera unchanged if only one device available; note it in status.md).
- [ ] Simulated fall → caretaker-targeted `safety_alerts` record; email sent when configured; absent from `GET /alerts/patient`.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
