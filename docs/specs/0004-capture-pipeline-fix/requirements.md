# 0004 Capture Pipeline Fix Requirements

## Goal

Make `Capture/camera_feed.py` correct, configurable, and decoupled: fix the mis-nested main loop, load the YOLO model from a CWD-independent path, move camera configuration into env vars, give each camera its own recording dimensions, and route fall alerts through the alert service instead of inline Gmail.

## Functional Requirements

- The per-frame pipeline (detection → recording state machine → fall alerting → HUD drawing) runs once per camera frame, not nested inside the YOLO results iteration.
- YOLO weights load from a path derived from the module location (`Capture/trained-weights/best.pt`), overridable via `FALL_MODEL_PATH`.
- Camera setup comes from env: `CAMERA_INDICES` (default `1,2`) and `CAMERA_ROOM_MAP` (default `1:0,2:1`), replacing the hardcoded lists.
- Each camera's `VideoWriter` uses that camera's actual frame dimensions (today all writers use camera 0's dims, corrupting output when resolutions differ).
- A confirmed fall creates an alert record through `alert_service` (alert type `fall`, target role `caretaker`) which owns delivery; the Gmail send becomes an alert-service channel invoked for caretaker-targeted alerts when configured. `camera_feed.py` no longer imports Gmail code directly.
- Recording start/stop, screenshot extraction, audio capture, and queue handoff behavior are preserved (person detected → record; 2s absence → stop → queue).
- Misleading comments (buffer durations that contradict constants) are corrected.

## Technical Constraints

- The capture process is synchronous/threaded (OpenCV loop); calling the async `alert_service` must not block frame processing — use the existing queue thread's event loop or a fire-and-forget thread, mirroring how `VideoProcessingQueue` already bridges sync→async.
- Fall-detection tuning (0.50 confidence, 3.5s stability window) is preserved exactly.
- Path values handed to the queue stay in the spec-0002 stored form.

## Non-Requirements

- No change to YOLO model weights or training.
- No new detection features; no multi-person logic.
- The `audio_capture.py` join-then-read race may be tightened opportunistically (copy frames under the lock) but is not a gate.

## Acceptance Criteria

- With two cameras of different resolutions, both produce playable MP4s.
- Running `python Capture/camera_feed.py` from a directory other than the repo root works (weights load, outputs land under project `Storage/`).
- A simulated fall (or test video) produces: a `safety_alerts` record targeting the caretaker, and — when Gmail + `FALL_ALERT_RECIPIENT_EMAIL` are configured — the email; with neither configured, the alert record still persists with an honest `delivery_status`.
- Person-exit still stops recording after the buffer and the event flows through the queue → consolidator → Mongo unchanged.
- `python -m compileall -q Capture` passes; the restructured functions are unit-testable and covered for the state machine's start/stop transitions (pure-logic tests with fake detections).
