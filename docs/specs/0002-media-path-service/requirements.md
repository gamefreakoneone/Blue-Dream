# 0002 Media Path Service Requirements

## Goal

One module owns every media-path conversion. MongoDB stores portable relative paths, the API always returns URL paths, and the web/mobile clients stop guessing. Legacy documents with absolute Windows paths keep working through read-time normalization — no database migration.

## Functional Requirements

- New module `Blue_dream_agents/media_paths.py` providing:
  - `to_stored_path(path)` — any absolute/relative path → relative POSIX stored form (`Storage/...` or `Capture/...`).
  - `to_fs_path(stored)` — stored form → absolute filesystem path under `MEDIA_ROOT`.
  - `to_url_path(stored)` — stored form → URL path (`/storage/...` or `/capture/...`), `None` for empty/unmappable input.
  - `normalize_stored_path(raw)` — legacy absolute Windows/POSIX paths → stored form (locates the `Storage`/`Capture` segment and re-roots).
- All writers store the relative POSIX form: capture pipeline outputs, consolidator, object detector highlights, alert-service highlights.
- All internal readers (YOLO screenshots, vision checks, safety agent, alert highlighting) resolve through `to_fs_path`.
- Every API response field carrying an image/video path returns the URL form.
- `MemoryEvent` read-time normalization runs `normalize_stored_path` on `screenshot_path`, `video_path`, `audio_path` so legacy docs behave identically to new ones.
- `UI/script.js` and `Mobile/lib/api.js` stop substring-hacking: web uses `image_path` as-is (same origin); mobile prefixes `EXPO_PUBLIC_API_BASE_URL`.
- The alert-service highlight output directory is resolved against the project root, not the current working directory.
- `.env.example` `CHROMA_PERSIST_DIR` matches the code's absolute-by-default behavior (documented, or the setting made root-relative in code).

## Technical Constraints

- `MEDIA_ROOT` env var, defaulting to the repository root (derived from module location, like the existing `Storage/chroma` default in `llm/settings.py`).
- Dedupe-by-`video_path` in the consolidator must keep matching legacy variants (compare normalized stored forms on both sides).
- No bulk Mongo migration; an optional one-shot script is out of scope.

## Non-Requirements

- No changes to what media is captured or how it is recorded.
- No auth on static mounts (unchanged demo posture).

## Acceptance Criteria

- New ingested events carry relative POSIX paths in Mongo.
- `/query` object answers return `image_path` starting with `/storage/` or `/capture/`; the image renders in the web UI without the old rewrite hack.
- A legacy event with an absolute `C:\...\Storage\...` screenshot path still resolves: internal reads find the file and API responses map it to `/storage/...`.
- Alert detail `image_path`/`original_image_path` are URL paths and render.
- Highlight files land under the project-root `Storage/highlighted/` regardless of the process CWD.
- `pytest tests/test_media_paths.py` passes, including Windows-backslash legacy inputs.
