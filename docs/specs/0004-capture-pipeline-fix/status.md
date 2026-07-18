# 0004 Capture Pipeline Fix Status

## Status

Completed on 2026-07-18. Qwen/OSS video understanding and the first provider-backed live ingestion gate remain exclusively scoped to spec 0005.

## Delivered

- Replaced parallel camera dictionaries with validated `CaptureConfig` and per-camera `CameraRig` state.
- Hoisted detection summarization, recording transitions, fall confirmation, and HUD rendering to run exactly once per frame, including empty model results.
- Made camera indices, room mapping, model path, resolution/FPS, confidence, absence debounce, and fall stability configurable while preserving tuned defaults.
- Made model/output resolution CWD-independent and each writer use its camera's actual first-frame dimensions.
- Kept the queue payload contract in stored-path form and made its event loop continuously available for non-blocking fall-alert submission.
- Moved fall persistence and caretaker Gmail delivery into `alert_service`; hazard alerts default to `hazard`/`patient`, falls use `fall`/`caretaker`, and patient listing filters by role.
- Documented capture variables and retained the optional audio-lock cleanup as intentionally out of scope.

## Verification Evidence

- Focused capture gate: `conda run -n Project-Memoria python -m pytest tests/test_capture_state.py -q` — **15 passed** in 5.17s.
- Full suite: `conda run -n Project-Memoria python -m pytest tests/ -q` — **68 passed** in 5.35s.
- Compilation: `conda run -n Project-Memoria python -m compileall -q Capture Blue_dream_agents` — passed with no compile errors.
- Diff hygiene: `git diff --check` passed. The repository's expected LF→CRLF notices remain informational on Windows.
- Tests cover start/continue/stop transitions, the exact 2s debounce, 3.5s single-fire fall guard, empty/multiple result aggregation, strict/default config parsing, module-relative weights, per-rig writer dimensions, idle event-loop responsiveness, and the unchanged queue payload.
- Alert tests prove insert-before-delivery ordering, `fall`/`caretaker` fields, honest missing-config status, configured Gmail work running off the event-loop thread, and explicit patient-role filtering.
- Live capture launched by absolute script path from `C:\tmp`; the module-relative YOLO weights loaded and runtime outputs landed under the repository `Storage/` tree.
- The user observed the camera window and fall detection. A completed walk-in/walk-out recording, `camera_1_2026-07-18_00-53-02.mp4`, opened successfully at **1920x1080**, **53 frames**, **3,425,426 bytes**, with a 163,465-byte MP3 and 231,924-byte end-state screenshot.
- Only one camera was available for the gate, so the spec's allowed single-camera fallback was used; the two-camera mixed-resolution check remains a demo-time hardware check.
- A genuine fall alert persisted in local Mongo as `alert_type="fall"`, `target_role="caretaker"`, room 0, with a stored fall screenshot and `delivery_status="not_configured"` because the recipient was blank at capture time. A live TestClient request to `GET /alerts/patient?status=all` returned HTTP 200 with **zero fall alerts visible**.
- The recipient is now configured in the untracked `.env`, but no real caregiver email was sent implicitly. The configured path is verified with a mocked Gmail sender; a live external email remains an optional operator check.
- Provider-backed media understanding and Mongo event insertion were not run here: spec 0005 explicitly owns the mandatory DashScope/OSS spike, Qwen ASR/video wiring, and first live provider end-to-end gate. Spec 0004 verifies the exact queue handoff without exporting private media.
- Known non-fatal output: the existing Starlette deprecation warning, Python 3.13 `audioop` deprecation warning from pydub, and conda's missing OpenCL `temp.txt` cleanup message.

## Commit Evidence

- Implementation commit: `653a652` (`feat: implement spec 0004 capture pipeline fix`).
