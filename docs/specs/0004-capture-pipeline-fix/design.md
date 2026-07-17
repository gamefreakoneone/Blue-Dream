# 0004 Capture Pipeline Fix Design

## Contracts You Must Not Break

- Queue handoff: `camera_feed` → `VideoProcessingQueue` → `consolidator_agent` with the same task payload fields (video/audio/screenshot stored paths, room number, timestamps).
- Fall-detection tuning: confidence 0.50, stability window 3.5s, detection buffer 2s.
- Room mapping semantics: room `0 = Bedroom`, `1 = Living Room` (defaults preserved via `CAMERA_ROOM_MAP`).
- `Capture/trained-weights/best.pt` location.

## Intentional Design Decisions (do not "fix" these)

These look like bugs but are deliberate, user-confirmed choices; the restructure must preserve the behavior:

- **2s no-person buffer before stopping a recording**: a debounce against YOLO false negatives and the person briefly leaving the frame. Recording must not be interrupted by a one-second detection gap. Keep the behavior; only the misleading comments get fixed.
- **End-of-event screenshot** (last frame, captured after the buffer expires): intentionally shows the room *after* the person leaves — the end state is the best evidence for object-finding and unattended-hazard checks (nothing is occluded by the person).
- **`fps=20` recording**: an accepted tradeoff for modest hardware; keep as the default (env-tunable is fine).
- **Default-microphone audio**: single-occupant, two-room home with one active camera at a time — the default input device is correct. Do not add per-camera microphone plumbing; at most keep an optional `device_index` passthrough on `AudioRecorder`.
- **Fall tuning (0.50 confidence, 3.5s stability, once-per-recording alert guard)**: tuned anti-false-positive/anti-spam values, not arbitrary; keep as defaults when making them env-configurable.

## The mis-nesting bug (the core fix)

Current shape (`Capture/camera_feed.py` ~219–370): the recording state machine, fall alerting, and drawing sit **inside** `for result in results:`. Ultralytics returns one `Results` per frame, so it works accidentally; an empty list would skip all recording logic silently.

Target shape — extract pure functions and hoist the per-frame logic out of the results loop:

```python
def load_capture_config() -> CaptureConfig      # env parsing: CAMERA_INDICES, CAMERA_ROOM_MAP, FALL_MODEL_PATH, resolution/fps
def init_cameras(config) -> dict[int, CameraRig]  # capture handle + per-camera frame dims + writer factory
def summarize_detections(results) -> FrameDetections  # persons present?, fall boxes, confidences — consumes ALL results
def update_recording_state(rig, detections, now) -> RecordingAction  # pure state machine: start/continue/stop
def handle_fall_state(rig, detections, now) -> bool  # 3.5s stability window; returns fall_confirmed
def draw_hud(frame, detections, rig) -> None
def camera_feed() -> None  # thin loop: read → infer → summarize → state machine → act → draw
```

Per-camera state lives in one `CameraRig` dataclass (replaces the current eight parallel dicts keyed by camera index).

## Weights + config

```python
MODEL_PATH = Path(os.environ.get("FALL_MODEL_PATH", "")) or (Path(__file__).resolve().parent / "trained-weights" / "best.pt")
```

`CAMERA_INDICES=1,2` and `CAMERA_ROOM_MAP=1:0,2:1` parsed in `load_capture_config`; document both in `.env.example`. Fix the comment/constant mismatches (`DETECTION_BUFFER_SECONDS = 2` labeled "3-second"; the "5-second Buffer" comment on the 3.5s fall check).

## Per-camera VideoWriter dims

`init_cameras` captures `(width, height, fps)` per opened camera and the writer factory uses that rig's dims — replacing the current single `cameras[0]` read (~194–196).

## Fall alerts through the alert service

Remove the `GmailAgent` import/init and the inline email block (~37–79, 122–129). On confirmed fall:

```python
create_alert_sync(
    alert_type="fall", severity="high", target_role="caretaker",
    title="Possible fall detected",
    body=f"A possible fall was detected in the {room_name}.",
    room_number=room, screenshot_path=stored_screenshot_path,
)
```

- `alert_service` gains `alert_type` and `target_role` fields on the alert document (defaulting existing hazard alerts to `hazard`/`patient`) and a **caretaker email channel**: for `target_role="caretaker"` alerts, if Gmail credentials + `FALL_ALERT_RECIPIENT_EMAIL` are configured, send via the retained `send_alert_email` path (executor-wrapped — the Gmail client is synchronous); otherwise record `delivery_status="not_configured"`. Patient-targeted delivery behavior is unchanged.
- Sync→async bridge: add `alert_service.create_alert_sync(...)` that submits the coroutine to the `VideoProcessingQueue` thread's persistent loop (`asyncio.run_coroutine_threadsafe`) — the queue object is already available in `camera_feed`; pass its loop handle. Never block the frame loop on delivery.
- The recipient policy matches the product rule: **fall alerts go to the caretaker, never to the fallen patient.**

## GET /alerts filtering

`GET /alerts/patient` must continue returning only patient-targeted alerts (filter `target_role="patient"`), so fall alerts do not appear in the patient's mobile/web alert list. Caretaker alerts become visible in the spec 0012 dashboard.

## Opportunistic: audio_capture race

In `stop_recording` (`Capture/audio_capture.py` ~111), copy `self.frames` under the existing lock after the join before serializing. Small, safe, optional.

## Tests

`tests/test_capture_state.py` — pure-logic tests with fabricated `FrameDetections`:
- person appears → `start` action; person absent < buffer → `continue`; absent ≥ buffer → `stop`.
- fall detected continuously ≥ 3.5s → confirmed exactly once (no re-trigger while the fall persists).
- empty detections list handled (the old bug's regression test).
- `CAMERA_ROOM_MAP` parsing: valid, malformed, defaults.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/test_capture_state.py -q
conda run -n Project-Memoria python -m compileall -q Capture Blue_dream_agents
```

Live: run capture from a non-root CWD; walk in/out of frame → recording starts/stops, event reaches Mongo; simulate a fall (test clip or staged) → `safety_alerts` doc with `alert_type="fall"`, `target_role="caretaker"`, and email delivery when configured; confirm the fall alert does NOT appear in `GET /alerts/patient`.
