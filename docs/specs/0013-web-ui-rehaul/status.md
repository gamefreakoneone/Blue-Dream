# 0013 Web UI Rehaul Status

## Status

**Implemented — pending demo-morning phone validation.**

Phases A-E are implemented in order, all automated gates pass, and no cut line was exercised. This status must not be changed to Completed until the physical-phone checklist below has been run and its evidence recorded.

## Phase evidence

| Phase | Commit | Dated evidence |
|---|---|---|
| A — backend push, summaries, serving | `57c3bc7` | 2026-07-19 03:42 PT — `feat: add web push backend and reminder sweep (spec 0013)` |
| B — React PWA scaffold | `adbff9f` | 2026-07-19 03:49 PT — `feat: scaffold the Memoria React PWA (spec 0013)` |
| C — patient screens and notifications | `e6e692b` | 2026-07-19 04:06 PT — `feat: build patient PWA screens and notification flow (spec 0013)` |
| D — all stretch interactions | `20d5854` | 2026-07-19 04:12 PT — `feat: add PWA stretch interactions (spec 0013)` |
| E — cleanup, docs, final validation | this commit | `chore: complete spec 0013 cleanup docs and validation` |

All phase commits through D were pushed to `origin/hackathon` immediately. Phase E is pushed with this status update.

## Automated validation evidence

- Baseline before implementation: 129 tests passed in the `Project-Memoria` conda environment.
- Final gate: `conda run -n Project-Memoria python -m pytest tests/` → **143 passed, 2 warnings in 26.71s**. The first sandboxed attempt produced 10 temp-directory setup permission errors after 133 passes and no assertion failures; the identical command rerun with normal user temp access passed completely.
- Targeted httpx/FastAPI TestClient smokes: push endpoints, subscription upsert/unsubscribe, declared `sent|no_subscriptions|not_configured` test outcomes, 404/410 cleanup, unique index, hook dedupe/failure behavior, summaries filtering/serialization, and unchanged atomic proactive claim/ack semantics → **14 passed, 1 warning in 5.26s**.
- UI gate: `npm.cmd run build` with Vite 8.1.5 → **30 modules transformed**, `dist/index.html` 0.71 kB, CSS 19.96 kB, JS 227.05 kB; clean success.
- Built static state: `GET /` → 200 with `<title>Memoria</title>`; `GET /manifest.webmanifest` → 200 `application/manifest+json`.
- Missing-build state: `UI/dist` was reversibly renamed, isolated uvicorn booted successfully, `GET /push/vapid-public-key` → 200, and logs contained the exact required warning: `UI build not found at C:\Users\amogh\Desktop\Project Memoria\UI\dist; the API will run without the web UI. Run: cd UI && npm run build`. The bundle was restored and `/` returned 200 again.
- `pywebpush==2.3.0` is installed and pinned. UI exact pins: React 19.2.7, React DOM 19.2.7, Vite 8.1.5, `@vitejs/plugin-react` 6.0.3; Node 22.15.0, npm 8.15.0. `package-lock.json` is committed.
- VAPID keys were generated into the untracked root `.env`; no key material was printed or staged. `.env.example` documents `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`, and `REMINDER_SWEEP_SECONDS`.
- `Mobile/` was deleted completely: 24 tracked prototype files plus ignored `.expo`, `android`, `dist`, `node_modules`, `.env`, and `google-services.json` remnants. Dormant FCM backend code and `POST /devices/register` remain untouched.
- `adb` is not installed on this machine (`ADB_NOT_FOUND`), so USB/wireless and physical-device checks were intentionally not claimed.

## Chrome UI rehearsal

Chrome exercised the production `UI/dist` through `scripts/spec0013_ui_rehearsal.py`, an isolated FastAPI server with deterministic in-memory responses and no production MongoDB imports or writes.

- Phone viewport 430×932 and desktop viewport 1440×1000 rendered Chat, Reminders, Safety, Memories, and the caregiver/demo sheet with no console warnings or errors.
- Chat rendered a safety proactive bubble with entrance/highlight treatment and image, then acknowledged after render. A grounded query rendered an evidence image and the expanded `Memory used · 3 memories` panel with 5 considered / 3 packed / 2 excluded, similarity and final scores, and a pinned fact row.
- Reminders rendered Today/Later data; the event-reminder form was filled without a production write and enabled only after its required text/condition fields were present.
- Safety rendered a medium-severity highlighted card; the isolated `I'm okay` action returned the screen to its reassuring empty state.
- Memories rendered two profile facts, selected pinned state, and two newest-first daily summaries.
- Demo tools rendered the consolidation report (2 groups / 7 events / 2 summaries), kept the canned geofence-exit result inside the sheet, rotated the conversation session, and showed the declared not-configured push-test state.
- Visual comparison against the two approved concepts confirmed the warm high-contrast palette, large controls, emerald/amber hierarchy, evidence image cards, and emphasized proactive arrival. Generated local evidence (gitignored runtime artifacts):
  - `Proof/spec-0013/chrome-mobile-proactive-arrival.png`
  - `Proof/spec-0013/chrome-mobile-grounded-recall.png`
  - `Proof/spec-0013/chrome-mobile-memories.png`
  - `Proof/spec-0013/chrome-desktop-chat.png`

## Cut lines

None. Daily summaries, the event-reminder form, notification fallback/chime, and Memories all shipped. Every never-cut item shipped.

## Acceptance criteria still pending

- [ ] AC1: Android Add to Home Screen install and standalone launch with the Memoria icon.
- [ ] AC2: closed-app +2-minute time reminder → real OS notification → tap → exactly one highlighted reminder bubble in the ongoing thread.
- [ ] AC3: physical safety-pipeline hazard → closed-app push or foreground chime bubble with highlighted image → Safety → `I'm okay` acknowledgement.
- [ ] AC4: first real ingested event of the day → morning-report push and sun-styled proactive bubble.

The isolated browser rehearsal verified the UI/rendering mechanics for AC3 and the automated suite verifies the push/claim contracts, but those are not substitutes for physical-device evidence.

## Pending human validation (demo morning)

Run these steps in order and paste results/screenshots into this file before changing the ledger to Completed.

1. **Android install and permission (USB path)**
   - Install Android platform-tools if `adb` is still unavailable.
   - Enable Developer options and USB debugging; connect the phone.
   - Run `adb devices`, confirm the device is `device`, then run `adb reverse tcp:8000 tcp:8000`.
   - Start `uvicorn Blue_dream_agents.api:app --host 0.0.0.0 --port 8000` from the `Project-Memoria` conda environment.
   - In phone Chrome open `http://localhost:8000`, choose Add to Home Screen / Install app, launch the Memoria icon, and confirm standalone display.
   - Tap **Enable** in Memoria (the only permission trigger), choose **Allow** in Android, and confirm the card changes to enabled.

2. **Closed-app reminder, notification tap, and single highlighted bubble**
   - In Reminders create a one-time reminder due two minutes ahead.
   - Return to Chat, note the ongoing thread/session, then fully close/background the PWA and lock the phone.
   - Confirm one OS notification arrives. Tap it.
   - Confirm the same conversation opens at `/#chat`, the pending reminder renders exactly once at the bottom with the blue highlighted-arrival treatment, auto-scrolls into view, and accepts a contextual follow-up. Capture the notification and opened-thread screenshots.

3. **Hazard path**
   - Run the existing spec 0008 safety rehearsal/capture recipe with an image-bearing actionable hazard.
   - Repeat once with the app closed (OS push) and once visible (no OS toast; soft chime + immediate amber bubble).
   - Confirm the highlighted image appears in Chat and Safety, then tap **I'm okay** and verify the alert leaves the open list.

4. **Morning report**
   - Before the first real camera event of the demo day, open/close the PWA as desired and ingest that event.
   - Confirm one `Good morning` notification and one sun-styled morning-report bubble; verify no duplicate on the next event.

5. **Pinned grounded recall**
   - Ensure one useful profile/event memory is pinned.
   - Ask a grounded object/activity question and confirm answer text, highlighted evidence image, and an expanded Memory Used panel showing considered/packed/excluded counts, similarity/final scores, and the pinned star.

6. **Demo tools and foreground notification**
   - With the app visible, run **Send test**: confirm no OS toast, immediate page handling, and the foreground chime/highlight path.
   - Run memory cleanup and confirm the inline counts. Run the canned geofence exit and confirm its result appears only inside the demo sheet with no patient-tab change.

7. **Wireless adb and lock-screen push**
   - On Android 11+, enable Wireless debugging and choose Pair device with pairing code.
   - Run `adb pair <phone-ip>:<pair-port>`, enter the code, then `adb connect <phone-ip>:<port>` and `adb reverse tcp:8000 tcp:8000`.
   - Unplug USB, close the PWA, lock the phone, trigger a test/reminder push, and confirm it appears on the lock screen.
   - Tap it and confirm the app loads the pending message through the wireless tunnel. Keep the USB recipe as the rehearsed fallback.

8. **Final contract rehearsal**
   - Exercise `POST /query`, `POST /conversation/reset`, open/detail/ack alert endpoints, all geofence endpoints, `/proactive/pending` + ack, `POST /devices/register`, and `/storage`/`/capture` media URLs.
   - Confirm pending proactive messages still claim atomically once, patient errors remain fixed/reassuring, and no raw exception text appears.
