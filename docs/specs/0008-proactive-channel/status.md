# 0008 Proactive Channel Status

## Status

Completed.

## Verification Evidence

### Automated suite

- `conda run -n Project-Memoria python -m pytest tests/ -q`
- Result: **118 passed**, 2 pre-existing deprecation warnings, 0 failures/errors in 14.68 seconds.
- The exact command was run outside the filesystem sandbox after the sandbox-only baseline produced temporary-directory permission errors.

### Isolated live trigger/API rehearsal

- `powershell -ExecutionPolicy Bypass -File scripts/run_spec0008_rehearsal.ps1`
- Used MongoDB `127.0.0.1:27028` and temporary files under `C:\tmp\spec0008-rehearsal`; the normal MongoDB port 27017 and `Storage/chroma` were never modified. The guarded runner removed its temporary database and API processes on exit.
- Live Qwen structured calls produced one first-event morning report and one matching living-room event reminder. The same event's second same-day evaluation stayed deduplicated; a 12:00 event outside the 06:00-11:00 window produced zero messages.
- The privacy-safe persisted hazard-event replay used existing captured image evidence and produced one image-bearing safety message. The API poll delivered exactly four trigger messages (morning, event reminder, safety, due time reminder); a second browser session received zero duplicates.
- All four messages appended as assistant turns, acknowledged successfully, and did not reappear. The deliberately expired warning remained pending and undelivered. The daily reminder rolled to the next day; the undated event reminder remained active for next-day re-arm.
- A raw 67 MB camera/audio clip upload was intentionally not repeated: approval was denied because it would export private local surveillance media to external OSS/Qwen. The rehearsal therefore begins from the factual hazard-event boundary. Full consolidator trigger isolation is covered by pytest, while Qwen video/OSS behavior remains the independently completed spec 0005 evidence.

### Rendered web UI

- Flow: `/` loads → five-second poll claims the seeded warning → a distinct `Memoria noticed` card renders → UI posts acknowledgement → reload shows no duplicate.
- The in-app Browser plugin reported no available browser backend. Validation fell back to Playwright 1.61.1 using the installed Chrome; no browser dependency was added to the repository.
- Desktop `1440x1000` and mobile `390x844` checks confirmed the title, meaningful content, proactive label/text, loaded image, and safe action link (`target="_blank"`, `rel="noopener noreferrer"`). Before reload there was one proactive card; after reload there were zero. Browser console warnings/errors: zero.
- Rendered testing found that an asynchronously loaded image could expand after the first scroll. Adding an image-load scroll refresh fixed it; the desktop screenshot then showed the complete label, bubble, image, and action button. Evidence remains outside the repository at `C:\tmp\spec0008-ui-desktop.png`, `C:\tmp\spec0008-ui-mobile.png`, and `C:\tmp\spec0008-ui-message-desktop.png`.

### Commit evidence

- Implementation commit: recorded by the follow-up evidence commit.
