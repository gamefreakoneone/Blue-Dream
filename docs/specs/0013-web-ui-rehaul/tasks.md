# 0013 Web UI Rehaul Tasks

Time boxes assume one overnight session (~6h). Phases run in order; the cut lines at the bottom are pre-authorized — exercise them rather than shipping a half-working never-cut item. Commit at the end of each phase with a descriptive message (dated commits are submission evidence).

## Prerequisites

- [x] Baseline: `python -m pytest tests/` green (129 tests); Node + npm available (`node -v`, `npm -v`); conda env `Project-Memoria` active.
- [ ] `adb devices` shows the phone (USB debugging on). If platform-tools are missing, note it and continue — laptop Chrome is the fallback demo path; do not burn more than 10 minutes here.

## Phase A — Backend push + endpoints (~75 min) [NEVER CUT]

- [x] Pin `pywebpush` in `requirements.txt` and install it in the conda env.
- [x] Write `scripts/generate_vapid_keys.py` (py_vapid), run it, put `VAPID_PRIVATE_KEY`/`VAPID_PUBLIC_KEY` in `.env`, document all four new env vars in `.env.example`.
- [x] `db_client.py`: `get_push_subscriptions_collection` + unique-endpoint index in `ensure_push_indexes`, wired into both process-init paths (API lifespan and capture init — same pattern as alert indexes).
- [x] `Blue_dream_agents/web_push.py` per design: config, `send_to_patient_subscriptions`, `send_for_proactive_message`, 404/410 auto-disable, `asyncio.to_thread`, not-configured no-op. No FastAPI imports.
- [x] `api.py`: `GET /push/vapid-public-key`, `POST /push/subscribe` (upsert), `POST /push/unsubscribe`, `POST /push/test`; `GET /memory/summaries?days=`; reminder sweep loop in lifespan (`REMINDER_SWEEP_SECONDS`, default 30, 0 disables, cancelled on teardown); root mount retarget `UI/` → `UI/dist` with guarded warning when dist is missing.
- [x] Send hook in `proactive_service.create_message` — insert path only, never the dedupe early-returns, exception-safe.
- [x] Tests: `tests/test_push_endpoints.py`, `tests/test_web_push_hook.py`, `tests/test_memory_summaries_endpoint.py`; full suite green.

## Phase B — PWA scaffold (~60 min) [NEVER CUT]

- [x] Scaffold Vite + React in `UI/` (first task: `npm install` — surface registry problems early). Exact-pinned deps (`react`, `react-dom`; dev `vite`, `@vitejs/plugin-react`), commit `package-lock.json`. Keep `slime_logo.png`/`favicon.ico`; delete old `index.html`/`script.js`/`styles.css` only after porting their chat/recall-debug/proactive logic as reference.
- [x] `vite.config.js` dev proxy for all API prefixes listed in design.
- [x] `public/manifest.webmanifest` and `public/sw.js` with all five events exactly per design (network-only fetch; foreground visible-client check; `tag = message_id`); SW registration in `main.jsx`.
- [x] Icons 192/512/maskable-512 generated from `slime_logo.png` (one-off Pillow script is fine).
- [x] App shell: `TabBar`, `theme.css` tokens, hash navigation, `api.js`.
- [x] `npm run build` → confirm FastAPI serves `UI/dist` at `/` and DevTools shows the app installable (manifest + SW detected).

## Phase C — Screens (~150 min)

- [x] **ChatScreen** [NEVER CUT]: `/query` flow with typing indicator, image cards, `MemoryUsedPanel`, `useProactivePoll` (5s, localStorage session id, pause on hidden, immediate poll on SW message + visibility regain), `ProactiveBubble` per-trigger styling + ack + highlight/auto-scroll arrival, notification-enable card. Showcase-grade polish per the design's visual direction.
- [x] **push.js enable flow** [NEVER CUT]: gesture → permission → subscribe → `POST /push/subscribe`; status handling for unsupported/denied/enabled.
- [x] **RemindersScreen** [NEVER CUT]: list, Today/Later, Done, time-based create form.
- [x] **SafetyScreen** [NEVER CUT]: open alerts with geofence types filtered out, highlighted image, severity tint, "I'm okay" ack, reassuring empty state.
- [x] **DemoToolsSheet** [NEVER CUT]: push status/enable/test, consolidation + inline report, geofence-exit simulation (inline result only), conversation reset, refresh-app (SW unregister + reload).
- [x] **MemoriesScreen** [CUT LINE 4]: profile facts + pin/hide. If cut, move facts + pin into DemoToolsSheet so the pinned-memory demo beat survives.

## Phase D — Stretch (~45 min, in order; each independently cuttable)

- [x] "Your days" daily-summaries section on MemoriesScreen (the Phase A endpoint ships regardless). [CUT LINE 1]
- [x] Event-based reminder create form (otherwise create event reminders via curl for the demo). [CUT LINE 2]
- [x] In-page `Notification` fallback in the poll loop + soft chime on proactive arrival. [CUT LINE 3]

## Phase E — Cleanup, docs, validation (~45 min) [NEVER CUT]

- [x] Delete `Mobile/`: `git rm -r Mobile` + remove untracked `node_modules` from disk.
- [x] Docs, all in the same change:
  - `docs/FEATURE_STATUS.md` — 0013 row status/evidence; keep 0009 demoted note current.
  - `AGENTS.md` Project Areas — `UI/` is now the Vite + React PWA built to `UI/dist` (`npm run build` required); remove the `Mobile/` bullet.
  - Root `requirements.md` — Non-Goals: Expo app deleted (this spec); web push now in scope; native mobile push stays a non-goal. Core Requirements: proactive channel line gains "web push wake-up channel".
  - `TECHNICAL_DESIGN.md` — Interaction layer paragraph (React PWA + web push, Mobile removed); New-endpoints table rows for `/push/*` and `GET /memory/summaries` (spec 0013); env surface additions; one line marking FCM delivery + `/devices/register` dormant.
  - `README.md` — build/run: `cd UI && npm install && npm run build`, uvicorn unchanged, the `adb reverse tcp:8000 tcp:8000` recipe (USB **and** the wireless-debugging variant from design.md), notification-permission step, `npm run dev` dev-mode note, SW unregister recipe.
  - `docs/specs/0012-openai-week/tasks.md` — annotate `GET /memory/summaries` as delivered by 0013 (leave `/alerts/recent` to 0012).
  - This spec's `status.md` + `tasks.md` checkboxes updated together per the Update Rule.
- [x] `python -m pytest tests/` green; `npm run build` clean; commit.

## Manual validation checklist (record evidence in status.md)

- [ ] Laptop Chrome `http://localhost:8000`: install prompt available, enable notifications, `POST /push/test` produces an OS notification.
- [ ] `adb reverse tcp:8000 tcp:8000`; phone Chrome → `http://localhost:8000`; Add to Home Screen; standalone launch with the Memoria icon.
- [ ] On the phone: enable notifications; create a reminder due +2 min; **close the app**; the OS notification arrives; tapping it opens the PWA on Chat and the reminder bubble renders exactly once, highlighted, in the ongoing thread.
- [ ] Foreground case: with the app open, trigger `POST /push/test` — no OS toast; the page receives the SW message (chime/immediate poll path).
- [ ] Hazard via the existing safety pipeline (0008 rehearsal recipe): push + amber bubble with highlighted image; alert on Safety; "I'm okay" acks.
- [ ] Morning report: first captured event of the day → push + sun bubble (rehearse tonight via the 0008 recipe if possible; otherwise verified live tomorrow morning before the video).
- [x] Grounded recall query → answer + highlighted image + "Memory used" panel including a pinned row. (Verified against the isolated Chrome rehearsal; live provider replay remains in the morning runbook.)
- [x] Demo tools: consolidation report renders inline; geofence simulation succeeds with zero patient-screen change. (Verified against isolated in-memory endpoints; no production collections were changed.)
- [ ] Untethered check (Android 11+): pair Wireless debugging, `adb connect` + `adb reverse` over Wi-Fi, unplug USB — with the app **closed** and no cable, a push notification arrives on the lock screen; tapping it opens the app and the thread loads through the wireless tunnel. (USB cable remains the rehearsed fallback.)
- [x] Contract smokes: `/query`, `/conversation/reset`, alert endpoints, geofence endpoints all behave unchanged.

## Cut-order summary (if the night runs short)

1. Daily-summaries UI → 2. event-reminder form → 3. notification fallback/chime → 4. Memories tab (facts relocate to demo tools).
Never cut: the push chain end-to-end, ChatScreen + recall debug + proactive bubbles, Reminders list/done/time-create, Safety, PWA install, mount retarget, `Mobile/` deletion, docs.
