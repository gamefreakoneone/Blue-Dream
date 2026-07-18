# 0002 Media Path Service Status

## Status

In progress as of 2026-07-17. Implementation and automated contracts are complete; live ingestion validation is now assigned to the spec 0005 Qwen ASR gate, and the image-bearing alert check remains unavailable in the current data.

## Verification Evidence

- Starting boundary: clean `hackathon` branch; spec 0001 was completed and the baseline suite passed with **23 tests**.
- Compilation: `conda run -n Project-Memoria python -m compileall -q Blue_dream_agents Capture` passed.
- Required validation: `conda run -n Project-Memoria python -m pytest tests/ -q` passed with **34 tests** in 5.02s. The existing third-party `StarletteDeprecationWarning` remains unrelated; conda also prints the known non-fatal missing OpenCL `temp.txt` cleanup message.
- Path contracts: tests cover Windows/POSIX legacy paths, stored and `Capture/` forms, case-insensitive mounts, empty/unmappable values, round trips, canonical Mongo writes, read-time normalization, CWD-independent output, legacy dedupe, and object/alert response URLs.
- Live legacy path: `C:\Users\amogh\Desktop\Blue-Dream\Storage\screenshots\camera_1\camera_1_2026-05-18_10-05-05.jpg` normalized to `Storage/screenshots/camera_1/camera_1_2026-05-18_10-05-05.jpg`, resolved to an existing file under the current project, and mapped to `/storage/screenshots/camera_1/camera_1_2026-05-18_10-05-05.jpg`.
- Static serving: the normalized legacy screenshot returned HTTP 200 as `image/jpeg` with 377,251 bytes through the `/storage` mount.
- Live dedupe: querying Mongo with the new relative video path and the consolidator's candidate set matched legacy event `6a0b46d855d9f724b0e3cff0`, whose stored value still uses the old absolute `Blue-Dream` root. No migration was performed.
- CWD independence: from `C:\tmp`, `resolve_output_dir("Storage/highlighted")` resolved to `C:\Users\amogh\Desktop\Project Memoria\Storage\highlighted`.
- Live ingestion history: a genuine unprocessed recording (`camera_1_2026-05-10_22-20-16.mp4`) previously stopped before insertion because the old OpenAI transcription credential was absent; Mongo remained at 40 events and no synthetic event was inserted. The rebuild no longer waits for that key: this pending live-ingestion check is superseded by the spec 0005 Qwen ASR validation.
- Live alert limitation: Mongo currently contains four alerts and zero image-bearing alerts, so a real alert-detail render could not be exercised without fabricating patient data. The mocked alert-detail contract and URL conversion pass in pytest.
- Live object-query rendering remains intentionally deferred to spec 0005, as required by this spec's task file.
- Implementation commit: this spec-only commit (SHA reported in the implementation handoff). The feature remains In progress until the deferred spec 0005 Qwen ingestion/object checks and an available image-bearing alert check are completed.
