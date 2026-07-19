# 0013 Web UI Rehaul Design

## Contracts you must not break

- `POST /query` request/response shape (`JeevesResponse`), `POST /conversation/reset`.
- All alert endpoints and the `serialize_alert` shape; all geofence endpoints (`GET/PUT /geofence/current`, `POST /geofence/events`).
- `GET /proactive/pending` atomic pending→delivered claim semantics and response shape; `POST /proactive/{id}/ack`.
- `POST /devices/register` (dormant but stable).
- `/storage` and `/capture` static mounts; `image_path` leaving the API is always a URL path.
- The root UI mount changes **target directory only** (`UI/` → `UI/dist`) — an implementation detail, not a contract.

## Visual direction

This is judged on camera. ChatScreen and the notification moments are the showcase: considered typography (one display + one text face max, system-font fallbacks fine), a warm high-contrast palette evolved from the existing emerald identity, smooth bubble entrance animations, image cards for highlighted hazards, distinctive proactive-bubble styling per trigger type, and a highlighted-arrival animation when a notification tap lands in the thread. Other screens reuse the same tokens (CSS custom properties in `src/theme.css`) but stay simpler. Dementia-appropriate rules everywhere: ≥18px base text, ≥48px tap targets, one primary action per card, warm reassuring copy, "hide" never "delete", red only for severe safety. No splash, no login — the app opens straight into Chat.

## Web Push architecture

### Module `Blue_dream_agents/web_push.py`

Plain-library code — Mongo + `pywebpush` only, **no FastAPI imports** — because proactive messages are created from both the API server process and the capture/ingestion process (same multi-process caution as alert init in `TECHNICAL_DESIGN.md`).

- Config from env: `VAPID_PRIVATE_KEY` (base64url string, not a file path), `VAPID_PUBLIC_KEY` (base64url uncompressed P-256 point, served to clients), `VAPID_SUBJECT` (default `mailto:memoria@localhost`). Missing keys → push disabled: every function no-ops returning `{"status": "not_configured"}`, one startup log line.
- `scripts/generate_vapid_keys.py`: uses `py_vapid` (installed with pywebpush) to print the two key lines for `.env`. Run once during implementation, before any push testing. Keys are secrets — `.env` stays untracked; document both vars in `.env.example`.
- `async send_to_patient_subscriptions(payload: dict) -> dict`: payload JSON `{title, body, tag, url, image, trigger_type, message_id}`. `pywebpush.webpush()` is sync → run per-subscription in `asyncio.to_thread`, TTL 600, `vapid_claims={"sub": VAPID_SUBJECT}`. On `WebPushException` with 404/410 (gone subscription) → set `enabled: false` on that subscription; all other errors log and never raise. Returns `{"status", "sent", "failed"}`.
- `async send_for_proactive_message(document) -> None`: maps `trigger_type` → title (`safety` → "Memoria noticed something", `reminder` → "A gentle reminder", `morning_report` → "Good morning"), body = message text, `tag` = `message_id`, `url` = `/#chat`, `image` = `to_url_path(normalize_stored_path(image_path))` when present.

### Storage

Mongo collection `push_subscriptions` (getter + `ensure_push_indexes` in `db_client.py`; unique index on `endpoint`; wire into both process-init paths like the alert indexes):

```json
{ "subscription_id": "ps_<hex12>", "endpoint": "<unique>", "keys": {"p256dh": "...", "auth": "..."},
  "role": "patient", "user_agent": "...", "enabled": true,
  "created_at": "...", "updated_at": "...", "last_result": null }
```

### Endpoints (api.py, Pydantic request models in the existing style)

```
GET  /push/vapid-public-key  -> {"enabled": bool, "key": str|null}
POST /push/subscribe         {"subscription": {"endpoint", "keys": {"p256dh","auth"}}, "role": "patient"}
                             -> {"ok": true, "subscription_id": "ps_..."}     (upsert on endpoint)
POST /push/unsubscribe       {"endpoint": str} -> {"ok": true}                (sets enabled:false; idempotent)
POST /push/test              -> {"status": "sent"|"no_subscriptions"|"not_configured", "sent": int}
```

### Send hook

In `proactive_service.create_message` (`proactive_service.py:96`), immediately after the successful `insert_one` — **not** on the `related_id` dedupe early-return paths:

```python
try:
    await web_push.send_for_proactive_message(document)
except Exception:
    logger.exception("Web push send failed for %s; message remains pending", message_id)
```

This one hook covers all four trigger moments (safety via `_create_proactive_for_alert`, time reminders via `check_due_reminders`, event reminders via `maybe_event_reminders`, morning report via `maybe_morning_report`). Fall alerts are caretaker-targeted and never reach this path — do not add a patient push for falls.

### Reminder sweep loop

`check_due_reminders` currently runs only inside `GET /proactive/pending` (poll-driven), so a closed app would never learn a reminder is due. Add a background task started in the api.py lifespan (reuse the `_background_tasks` pattern, `api.py:115`):

```python
async def _reminder_sweep_loop():
    while True:
        await asyncio.sleep(REMINDER_SWEEP_SECONDS)   # env, default 30; 0 disables the loop
        try:
            await proactive_service.check_due_reminders(now_local())
        except Exception:
            logger.exception("Reminder sweep failed")
```

Cancelled in lifespan teardown. The poll-path `check_due_reminders` call **stays**: the `related_id = f"{reminder_id}_{due_at}"` dedupe makes concurrent runs idempotent.

### Delivery ownership — the double-delivery rule (verbatim)

- Push fires once, at message creation; notification `tag = message_id` coalesces any OS-level repeat.
- `GET /proactive/pending` remains the **sole** `pending → delivered` state transition and the **sole** in-app renderer. The service worker never renders in-app content.
- `notificationclick` focuses an existing PWA window (navigating to `/#chat` if needed) or opens one; the app's normal poll then renders the bubble — because the app was closed, nothing polled, so the message is reliably still `pending`. No race.
- Expiry note: proactive messages expire (`PROACTIVE_EXPIRY_MINUTES`, default 60). A notification tapped hours later opens the app but the bubble no longer renders — accepted; the OS notification text itself carried the content.

### Notification behavior matrix (user-confirmed product behavior)

| Scenario | Behavior |
|---|---|
| App closed / other app / phone locked | Backend → browser push service → Chrome wakes `sw.js` → `showNotification`. Independent of the adb tunnel; needs internet on laptop and phone. Lock-screen display follows the phone's notification settings. |
| Notification tapped | Open/focus PWA on Chat in the **ongoing thread**; poll renders the pending message as a highlighted "Memoria noticed" bubble at the bottom, auto-scrolled. Conversation context preserved for follow-ups. |
| Push while app visible/focused | `sw.js` finds a visible focused client via `clients.matchAll` → skips `showNotification`, `postMessage`s the payload to the page; the app renders the bubble immediately with a soft chime + highlight (the poll remains the state-owning fallback renderer — the pushed `postMessage` only triggers an immediate poll, it does not render from payload). OS toast only when not visible. |

Implementation note for the foreground case: have the page message-handler simply trigger an immediate `/proactive/pending` poll rather than rendering from the push payload — this keeps the poll as the single renderer and makes the chime/highlight path identical for pushed and polled arrivals.

### Fallback ladder (degrade silently, top-down)

1. Web Push (secure context + permission granted + subscription registered) — works with the app closed.
2. In-page `Notification` API fired by the poll loop when permission is granted but no push subscription exists (page must be open). *(stretch)*
3. In-app proactive bubble + soft chime — always.

Laptop demo path: `http://localhost:8000` is a secure context on desktop Chrome, so tiers 1–3 behave identically there.

### Untethered phone demo (wireless adb)

Push **delivery** never needs the adb tunnel (backend → push service → phone Wi-Fi), so lock-screen notifications arrive with the phone fully disconnected. The tunnel is only needed when the app opens and loads data. For a cable-free demo (e.g. the walking-out-the-door event-reminder beat, tapping the notification while untethered):

1. Phone (Android 11+): Developer options → **Wireless debugging** → on → "Pair device with pairing code".
2. Laptop: `adb pair <phone-ip>:<pair-port>` (enter the code), then `adb connect <phone-ip>:<port>`.
3. `adb reverse tcp:8000 tcp:8000` — the localhost tunnel now runs over Wi-Fi.

Wireless adb is flakier than USB (drops on network changes; re-run `adb connect` + `adb reverse`). Runbook rule: rehearse wireless, keep the USB cable as the fallback. Document both recipes in the README.

## React app

### Stack decision

Handwritten `public/sw.js` + `public/manifest.webmanifest` instead of vite-plugin-pwa/workbox. Rationale: the PWA needs installability + push, not offline; workbox precaching is the #1 staleness risk during demo-morning iteration; the handwritten SW is ~50 lines and network-only. Runtime deps `react` + `react-dom` only; dev deps `vite` + `@vitejs/plugin-react`; all exact-pinned, lockfile committed. No router (hash navigation), no UI kit, no CSS framework.

### File layout (replaces `UI/` contents; keep `slime_logo.png` + `favicon.ico`, delete old `index.html`/`script.js`/`styles.css` — port their chat/recall-debug/proactive logic first, they are the reference)

```
UI/
  package.json            vite.config.js          index.html
  public/
    manifest.webmanifest  sw.js  favicon.ico  slime_logo.png
    icons/icon-192.png  icon-512.png  icon-maskable-512.png
  src/
    main.jsx  App.jsx  api.js  push.js  theme.css
    hooks/useProactivePoll.js
    components/TabBar.jsx  ChatMessage.jsx  ProactiveBubble.jsx  MemoryUsedPanel.jsx
               AlertCard.jsx  ReminderCard.jsx  FactCard.jsx  SummaryCard.jsx  BigButton.jsx
    screens/ChatScreen.jsx  RemindersScreen.jsx  SafetyScreen.jsx  MemoriesScreen.jsx  DemoToolsSheet.jsx
```

- Navigation: hash-based (`#chat | #reminders | #safety | #memories`) in App state — also means `StaticFiles(html=True)` needs no SPA path fallback.
- `api.js`: thin fetch wrapper, relative URLs (same-origin in prod, proxied in dev), friendly error strings, never raw exceptions.
- `push.js`: `getPushStatus()`, `enablePush()` (user gesture → `Notification.requestPermission()` → `pushManager.subscribe({userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key)})` → `POST /push/subscribe`), `disablePush()`.
- `vite.config.js` dev proxy: `/query /conversation /memory /reminders /proactive /devices /alerts /geofence /push /storage /capture` → `http://localhost:8000`.
- Session id: persisted UUID in `localStorage` (the old UI used `sessionStorage`; switch to `localStorage` so the thread survives the PWA being closed — required by the notification-tap behavior).
- Icons: generate 192/512/maskable-512 from `slime_logo.png` with a one-off Pillow resize (maskable = logo on padded solid background).

### manifest.webmanifest

```json
{ "name": "Memoria", "short_name": "Memoria", "start_url": "/", "display": "standalone",
  "background_color": "#f6faf8", "theme_color": "#047857",
  "description": "Your gentle memory companion.",
  "icons": [ { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
             { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
             { "src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" } ] }
```

### sw.js events (exact behavior)

- `install` → `self.skipWaiting()`; `activate` → `clients.claim()`.
- `fetch` → `event.respondWith(fetch(event.request))` — network-only, never caches (exists for installability confidence).
- `push` → parse `event.data.json()`; `clients.matchAll({type:'window', includeUncontrolled:true})`; if a client is visible/focused → `postMessage({type:'proactive-push', ...data})` and **skip** `showNotification`; else `showNotification(data.title, {body, tag: data.tag, icon: '/icons/icon-192.png', image: data.image || undefined, data: {url: data.url, message_id: data.message_id}})`.
- `notificationclick` → close; focus the first window client (navigate to `data.url` if elsewhere) else `clients.openWindow(data.url || '/')`.
- `pushsubscriptionchange` → re-subscribe with the stored applicationServerKey → `POST /push/subscribe`.

### Serving change (api.py:533-541)

Mount `UI/dist` at `/` (html=True, still mounted last). If `UI/dist` is missing, log a warning naming the build command (`cd UI && npm run build`) and skip the mount — the server still boots for API-only use and tests.

## Screens (component-level)

- **ChatScreen** — header (logo, friendly date, gear → DemoToolsSheet, notification-enable card until push is on); message list: `ChatMessage` (user/assistant; assistant renders `image_path` image card and `MemoryUsedPanel` when `data.recall_debug` present — collapsed by default, "Memory used · N memories" chevron; rows: type icon, date, similarity, final score, pinned star; excluded-count footer); `ProactiveBubble` (safety = amber + shield, reminder = blue + bell, morning report = sun; image card; acks via `POST /proactive/{id}/ack` after render; highlight + auto-scroll on arrival); `useProactivePoll` (5s interval, `session_id` from localStorage, pause when `document.hidden`, immediate poll on SW `proactive-push` message + on `visibilitychange` to visible); input row: large field + big send button; typing indicator during `/query`.
- **RemindersScreen** — `GET /reminders`; `ReminderCard` (text, friendly due phrase, recurrence chip, big "Done ✓" → `POST /reminders/{id}/done`); Today/Later grouping; "+ Add reminder" time form (text, `datetime-local`, daily toggle) → `POST /reminders`; event-type form (room, condition, window, valid-date) is stretch.
- **SafetyScreen** — `GET /alerts/patient?status=open`, client-side filter `!alert_type.startsWith("geofence")`; `AlertCard` (title, warm body, highlighted `image_path` image, severity tint, "I'm okay" → `POST /alerts/{id}/ack {"action":"ok"}`); empty state: "Everything looks safe right now. 💚".
- **MemoriesScreen** — "Things Memoria knows": `GET /memory/profile`, `FactCard` (text, category badge, pin toggle → `POST /memory/profile/{id}/pin`, discreet "hide" → `.../archive`) [core]; "Your days": `GET /memory/summaries?days=7` grouped by date, `SummaryCard` (room name, text) [stretch].
- **DemoToolsSheet** (modal sheet from the gear, header "Caregiver / demo tools") — push status pill + Enable + "Send test notification" (`POST /push/test`); "Run memory cleanup" → `POST /memory/consolidate` with the report rendered inline (groups formed / events consolidated / summaries created); "Simulate leaving home" → `POST /geofence/events {"event_type":"exit", latitude/longitude: canned out-of-radius coords, "device_id":"demo-web"}` with the result shown inline **here only** (no patient-facing geofence UI anywhere); "Start fresh conversation" → `POST /conversation/reset` + clear thread; "Refresh app" (SW unregister + reload) as the staleness escape.

## Backend deltas

- `GET /memory/summaries?days=7` → `{"summaries": [{summary_id, date, room_number, room_name, text, source_event_count, created_at}]}`, newest date first. Superset of the spec 0012 design shape so 0012 inherits it unchanged; read-only; JSON-safe.
- FCM delivery (`alert_service.py:590-697`) and `POST /devices/register` stay dormant and untouched. `deliver_patient_alert` returning `"no_devices"` after `Mobile/` deletion is harmless and expected.
- Delete `Mobile/`: `git rm -r Mobile` plus removing the untracked `node_modules` from disk.

## Env surface additions

`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT` (default `mailto:memoria@localhost`), `REMINDER_SWEEP_SECONDS` (default 30, `0` disables). All documented in `.env.example`.

## Tests

- `tests/test_push_endpoints.py` — vapid-public-key enabled/disabled states; subscribe validation (422/400 on missing endpoint/keys) and endpoint upsert idempotence; unsubscribe idempotence; `/push/test` with monkeypatched `webpush`; a 410 `WebPushException` disables the subscription.
- `tests/test_web_push_hook.py` — `create_message` calls the sender exactly once per new message and zero times on `related_id` dedupe; a sender exception never propagates; unconfigured keys → clean no-op.
- `tests/test_memory_summaries_endpoint.py` — shape, `days` filtering, JSON-safety, empty result.
- Full suite: 129 existing + new, all green. No JS test harness (explicit non-goal).

## Risks

1. **Overnight npm/network flakiness** — `npm install` is the first Phase B task; commit `package-lock.json`; if the registry is unreachable all backend phases still proceed.
2. **Service-worker staleness during rapid iteration** — network-only SW, `skipWaiting` + `clients.claim`, the demo-tools "Refresh app" button; document the DevTools → Application → Service Workers → Unregister recipe in the README.
3. **Windows adb availability** — verify `adb devices` early; if platform-tools are missing, install the standalone zip; laptop Chrome localhost is the rehearsed fallback demo.
4. **VAPID key generation** — offline operation (cryptography lib); run the script immediately after installing pywebpush; keys into `.env` before any push testing.
5. **Android notification permission needs a user gesture** — the enable card handles it; if permission was previously denied Chrome hides the prompt → reset via Site settings or use a fresh Chrome profile; rehearse once tonight.
6. **Time-reminder timing** — sweep and `due_at` both use `timezone_utils.now_local()`; the +2 minute manual check validates end-to-end before the video.
7. **Video recorded tomorrow morning** — hard stop ~9am PT July 20; the cut lines in `tasks.md` are pre-authorized; the morning report fires naturally on the first captured event of the day (no simulation needed — note this in the demo runbook).
