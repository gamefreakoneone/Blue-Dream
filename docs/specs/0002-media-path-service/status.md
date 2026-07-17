# 0002 Media Path Service Status

## Status

In progress as of 2026-07-17. Implementation and automated contracts are complete; the live ingestion and image-bearing alert checks remain blocked by the current environment.

## Verification Evidence

- Starting boundary: clean `hackathon` branch; spec 0001 was completed and the baseline suite passed with **23 tests**.
- Compilation: `conda run -n Project-Memoria python -m compileall -q Blue_dream_agents Capture` passed.
- Required validation: `conda run -n Project-Memoria python -m pytest tests/ -q` passed with **34 tests** in 5.02s. The existing third-party `StarletteDeprecationWarning` remains unrelated; conda also prints the known non-fatal missing OpenCL `temp.txt` cleanup message.
- Path contracts: tests cover Windows/POSIX legacy paths, stored and `Capture/` forms, case-insensitive mounts, empty/unmappable values, round trips, canonical Mongo writes, read-time normalization, CWD-independent output, legacy dedupe, and object/alert response URLs.
- Live legacy path: `C:\Users\amogh\Desktop\Blue-Dream\Storage\screenshots\camera_1\camera_1_2026-05-18_10-05-05.jpg` normalized to `Storage/screenshots/camera_1/camera_1_2026-05-18_10-05-05.jpg`, resolved to an existing file under the current project, and mapped to `/storage/screenshots/camera_1/camera_1_2026-05-18_10-05-05.jpg`.
- Static serving: the normalized legacy screenshot returned HTTP 200 as `image/jpeg` with 377,251 bytes through the `/storage` mount.
- Live dedupe: querying Mongo with the new relative video path and the consolidator's candidate set matched legacy event `6a0b46d855d9f724b0e3cff0`, whose stored value still uses the old absolute `Blue-Dream` root. No migration was performed.
- CWD independence: from `C:\tmp`, `resolve_output_dir("Storage/highlighted")` resolved to `C:\Users\amogh\Desktop\Project Memoria\Storage\highlighted`.
- Live ingestion limitation: a genuine unprocessed recording (`camera_1_2026-05-10_22-20-16.mp4`) was attempted, but `Audio_agent` rejected startup because `OPENAI_TRANSCRIBE_API_KEY` is absent. The failure occurred before insertion; Mongo remained at 40 events and the candidate count remained zero. No synthetic event was inserted.
- Live alert limitation: Mongo currently contains four alerts and zero image-bearing alerts, so a real alert-detail render could not be exercised without fabricating patient data. The mocked alert-detail contract and URL conversion pass in pytest.
- Live object-query rendering remains intentionally deferred to spec 0005, as required by this spec's task file.
- Implementation commit: this spec-only commit (SHA reported in the implementation handoff). The feature remains in progress until the two blocked live checks are completed.
