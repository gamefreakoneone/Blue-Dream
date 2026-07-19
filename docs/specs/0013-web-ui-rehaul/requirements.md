# 0013 Web UI Rehaul Requirements

## Goal

Replace the vanilla `UI/` single-pager with a **Vite + React installable PWA** that visibly demonstrates what the backend already does: real OS **push notifications** for reminders and dangerous-activity warnings (app closed, other app, or phone locked), a beautiful patient-first chat with proactive bubbles and the "Memory used" recall panel, and screens for reminders, safety alerts, and memories. Delete the prototype `Mobile/` Expo app entirely. No Expo, no Firebase console, no third-party push service — Web Push with self-generated VAPID keys and `pywebpush`.

This spec executes **before** spec 0009 (voice is demoted to a stretch goal, decided the morning of July 20). The Qwen demo video (spec 0011, submission July 20 2pm PT) is recorded on this UI; its scripted beats — hazard warning with highlighted image, event-triggered reminder, morning report, grounded recall with the recall-debug panel — are this spec's acceptance bar.

**This is a hackathon demo. The app must not just work — it must look beautiful on camera.** Polish priority: ChatScreen and every notification moment get showcase-grade treatment; other screens stay clean and consistent but simpler. No splash screen, no login, no onboarding — the app opens straight into Chat.

## Functional Requirements

### Web Push (no third-party accounts)

- New module `Blue_dream_agents/web_push.py` sending via `pywebpush` with self-generated VAPID keys (`scripts/generate_vapid_keys.py`, keys in `.env`). Must be plain-library code (Mongo + pywebpush only, no FastAPI coupling) because ingestion-driven triggers run in the capture process, not the API server.
- New Mongo collection `push_subscriptions` (unique index on `endpoint`).
- New endpoints: `GET /push/vapid-public-key`, `POST /push/subscribe`, `POST /push/unsubscribe`, `POST /push/test`.
- One send hook in `proactive_service.create_message` (after successful insert, never on the `related_id` dedupe early-returns) covers all four trigger moments: safety warning, time reminder, event-triggered reminder, morning report. Send failures log and never propagate.
- A reminder sweep loop in the API lifespan (`REMINDER_SWEEP_SECONDS`, default 30, `0` disables) runs `check_due_reminders` so time reminders push even when no client is polling `/proactive/pending`.
- Notification permission is requested only from a user gesture (an "Turn on gentle notifications" card/button) — never auto-prompted on load.
- Fall alerts remain caretaker-only (Gmail); they never reach the patient push channel.

### Notification behavior (state this matrix in the implementation)

| Scenario | Required behavior |
|---|---|
| App closed / other app / phone locked | Real OS notification: backend → browser push service → service worker `showNotification`. Delivery needs internet on laptop and phone, not the adb tunnel. |
| Notification tapped in the Android bar | Opens/focuses the PWA on Chat **in the ongoing conversation thread**. The message is still `pending` (nothing polled while closed), so the poll renders it as a highlighted "Memoria noticed" bubble at the bottom, auto-scrolled into view. Not a fresh conversation — follow-ups keep context. |
| Push arrives while the app is visible/focused | The service worker detects a visible focused client, **suppresses the OS notification**, and `postMessage`s the page; the app renders the bubble immediately with a soft chime and highlight. OS toast only when the app is not visible. |

- Double-delivery rule: **push is a wake-up channel only.** `GET /proactive/pending` remains the sole `pending → delivered` state transition and the sole in-app renderer. Notification `tag = message_id` coalesces OS-level repeats.
- Fallback ladder (degrade silently): Web Push → in-page `Notification` fired by the poll loop (stretch) → in-app proactive bubble (always).

### Installable PWA

- Vite + React; runtime npm deps `react` + `react-dom` only; dev deps `vite` + `@vitejs/plugin-react`; all exact-pinned with `package-lock.json` committed.
- **Handwritten** `public/sw.js` (install/activate, network-only fetch, push, notificationclick, pushsubscriptionchange) and `public/manifest.webmanifest` (`display: standalone`, icons generated from `slime_logo.png`). No workbox / vite-plugin-pwa — precaching is the biggest staleness risk on demo morning.
- Built to `UI/dist`; the api.py root static mount retargets from `UI/` to `UI/dist` with a guarded warning (server still boots API-only if the build is missing).
- Dev workflow: `npm run dev` with a Vite proxy to `http://localhost:8000`.
- Demo path: Android phone with `adb reverse tcp:8000 tcp:8000` browsing `http://localhost:8000` (secure context → service worker + push work over USB). Laptop Chrome at `localhost:8000` is the rehearsed fallback and behaves identically.

### Screens

Bottom tab navigation. Dementia-appropriate throughout: ≥18px base text, ≥48px tap targets, high contrast, warm reassuring copy, one primary action per card, "hide" never "delete", red reserved for severe safety.

1. **Chat (Home, default)** — showcase-grade. Message thread with the existing `POST /query` flow; assistant answers render `image_path` images and a collapsible **"Memory used"** recall-debug panel (`data.recall_debug`: considered/packed/excluded counts, per-memory type, timestamp, similarity, final score, pinned star) — this panel is a judge-facing bar raiser and must be preserved from the old UI. Proactive bubbles polled every 5s from `/proactive/pending` (then acked), styled distinctly per trigger type (safety = amber + shield, reminder = blue + bell, morning report = sun), with images and the highlighted-arrival animation after a notification tap. Notification enable card until push is on.
2. **Reminders** — list active reminders (`GET /reminders`) as large cards with friendly due phrasing and a big "Done" button; Today/Later grouping; create form for time reminders (text, date/time, daily toggle). Event-reminder create form is stretch.
3. **Safety** — open patient alerts (`GET /alerts/patient?status=open`, client-side filter removing `geofence_*` alert types), each with the highlighted hazard image, severity tint, warm body text, and an "I'm okay" acknowledgement. Empty state is reassurance copy.
4. **Memories** — "Things Memoria knows": profile facts (`GET /memory/profile`) with pin toggle and discreet hide/archive (core). "Your days": daily summaries via the new `GET /memory/summaries` (stretch).
5. **Demo tools** (gear icon opening a sheet, labeled "Caregiver / demo tools" — not a tab) — push status + enable + test notification; "Run memory cleanup" (`POST /memory/consolidate`) with the report rendered inline; "Simulate leaving home" (`POST /geofence/events`) shown inline here only — **geofence disappears from all patient-facing screens**; conversation reset; a hard-refresh button (SW unregister + reload) as the staleness escape hatch.

### Backend deltas (minimal)

- `pywebpush` pinned in `requirements.txt`; `web_push.py`; the four `/push/*` endpoints; the `create_message` hook; the reminder sweep loop.
- `GET /memory/summaries?days=7` pulled forward from spec 0012 with a superset shape so 0012 inherits it unchanged.
- Static mount retarget `UI/` → `UI/dist`.
- Delete `Mobile/` (git rm + untracked node_modules from disk). The FCM delivery code in `alert_service.py` and `POST /devices/register` stay **dormant and untouched** — removal buys nothing tonight and risks a stable surface.

## Technical Constraints

- No third-party services or accounts. The browser vendor's push endpoint (used transparently by the Push API standard) is transport, not an account dependency.
- Preserved contracts untouched: `POST /query` shape, `POST /conversation/reset`, all alert endpoints, all geofence endpoints, `/proactive/*` semantics (including the atomic pending→delivered claim), `POST /devices/register`, `/storage` + `/capture` static mounts.
- npm dependency list stays ≤5 packages; no router, no UI kit, no CSS framework (design tokens via CSS custom properties).
- All new backend responses JSON-safe; no raw exception text patient-facing (reuse the existing generic-error pattern).
- Existing pytest suite (129 tests) stays green; new endpoint/hook tests added. No JS test harness (explicit non-goal).

## Non-Requirements

- No offline support or precaching (the service worker is network-only by design).
- No auth (LAN demo posture). No iOS web push (Android + desktop Chrome only).
- No voice (0009 stretch), no caregiver dashboard (0012), no patient-facing geofence UI, no server-side geofence monitoring.
- No FCM removal, no native mobile push, no `Mobile/` replacement.
- No splash screen, login, or onboarding flow.

## Acceptance Criteria

Each maps to a demo beat for the spec 0011 video:

1. The PWA installs via Add to Home Screen on Android (adb reverse path) and launches standalone with the Memoria icon.
2. With the app **closed**, a time reminder due in +2 minutes produces a real OS notification; tapping it opens the app to Chat where the reminder bubble renders exactly once, highlighted, in the ongoing thread.
3. A hazard from the existing safety pipeline produces an OS notification (app closed) or an in-app chime bubble (app open), with the highlighted hazard image; the alert appears on Safety and "I'm okay" acknowledges it.
4. The morning report renders as a proactive bubble (and push) on the first ingested event of the day.
5. A grounded recall query returns an answer with a highlighted image and a "Memory used" panel showing packed memories including a pinned entry.
6. Demo tools: consolidation runs and shows its report inline; the geofence-exit simulation succeeds with zero patient-screen change; the test notification arrives.
7. Laptop Chrome at `http://localhost:8000` passes beats 2–6 identically (fallback demo path).
8. `python -m pytest tests/` fully green; `Mobile/` deleted; README/AGENTS/TECHNICAL_DESIGN/FEATURE_STATUS updated in the same change.
