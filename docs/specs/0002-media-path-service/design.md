# 0002 Media Path Service Design

## Contracts You Must Not Break

- `JeevesResponse` field names and types (`image_path` remains `string | null` — only its *content* becomes a URL path).
- Alert detail response fields (`image_path`, `original_image_path` keep their names).
- `/storage` → `Storage/`, `/capture` → `Capture/` static mounts in `api.py`.
- Consolidator idempotency: reprocessing a video whose path was stored in legacy absolute form must still dedupe.

## Module: `Blue_dream_agents/media_paths.py`

```python
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "")) or Path(__file__).resolve().parents[1]
_MOUNTS = {"storage": "Storage", "capture": "Capture"}

def to_stored_path(path) -> str | None      # absolute or messy input -> "Storage/x/y.jpg" (POSIX slashes)
def to_fs_path(stored) -> Path              # "Storage/x/y.jpg" -> MEDIA_ROOT / "Storage/x/y.jpg"
def to_url_path(stored) -> str | None       # "Storage/x/y.jpg" -> "/storage/x/y.jpg"
def normalize_stored_path(raw) -> str | None
```

`normalize_stored_path` logic: replace backslashes with `/`, then scan path segments case-insensitively for the first `storage` or `capture` segment and return from there with the canonical-case top directory (`Storage`/`Capture`). Input already in stored form passes through unchanged. Anything with no such segment returns the cleaned relative input as-is (do not crash on odd data). All four functions treat `None`/empty as `None`.

Also export `resolve_output_dir(stored_dir: str) -> Path` = `to_fs_path` + `mkdir(parents=True, exist_ok=True)` for highlight writers.

## Write-side changes (store relative POSIX)

- `Capture/camera_feed.py` builds screenshot/video/audio paths from `project_root` today; wrap the values it hands to the queue in `to_stored_path(...)`. (Only the path values change; the recording logic itself is spec 0004's job — coordinate but keep this change surgical.)
- `Blue_dream_agents/consolidator.py` (~lines 113–114): replace `os.path.normpath` persistence with `to_stored_path`; compute the dedupe candidates set from `normalize_stored_path(video_path)` plus the raw input so legacy-stored duplicates still match.
- `Blue_dream_agents/object_detector.py` (~347–352): its already-correct project-root resolution is replaced by `media_paths.resolve_output_dir("Storage/highlighted")`; the stored/returned path uses `to_stored_path`/`to_url_path`.
- `Blue_dream_agents/alert_service.py` (~181): `output_dir="Storage/highlighted"` becomes `resolve_output_dir("Storage/highlighted")` — this fixes the CWD-relative bug. Alert docs store the stored form.

## Read-side changes (resolve via `to_fs_path`)

Every `os.path.exists(...)`/`open(...)` on stored media paths goes through `to_fs_path(normalize_stored_path(p))`:

- `object_detector.py` screenshot existence check (~154) and the image bytes handed to vision checks.
- `safety_agent.py` final-screenshot check (~142).
- `alert_service.py` screenshot source for highlighting (~152).
- `gemini_spatial.py` image load + `_save_highlighted_image` output dir (accept a `Path` from callers; stop calling `.resolve()` on a bare relative string).

## Schema normalization

`Blue_dream_agents/memory_schema.py`: in the existing legacy-doc normalization path, run `normalize_stored_path` on `screenshot_path`, `video_path`, `audio_path`. This is the same mechanism already used for `event_id`/`room_name`/`semantic_text` fallbacks — legacy absolute paths become stored form the moment a doc is read, and nothing downstream sees the old form.

## API boundary (URL form out)

- `jeeves.py` / `object_detector.py`: wherever a result's `image_path` is set for the response, apply `to_url_path`.
- `alert_service.py` alert-detail serialization: `image_path`, `original_image_path` → `to_url_path`.
- Grep for `image_path` across `Blue_dream_agents/` to catch every assignment that flows into a response model.

## Client simplification

- `UI/script.js` (~402–431): delete the backslash-normalize + substring-search logic; use `data.image_path` directly as `img.src` (same-origin URL path). Keep the `onerror` fallback.
- `Mobile/lib/api.js` (~7–28): `rewriteImagePath` becomes: absolute `http(s)` URLs pass through; paths starting with `/` get `API_BASE_URL` prefixed; anything else returns as-is.

## Config fixes

- `.env.example`: set `CHROMA_PERSIST_DIR` guidance to match code behavior (absolute default derived from repo root; if set, use an absolute path). Add `MEDIA_ROOT` with default-blank documentation.

## Tests: `tests/test_media_paths.py`

- Legacy absolute Windows input `C:\Users\x\Desktop\Project Memoria\Storage\screenshots\a.jpg` → stored `Storage/screenshots/a.jpg` → URL `/storage/screenshots/a.jpg`.
- POSIX absolute input, already-stored input (idempotent), `Capture/...` input, empty/None input.
- Case-insensitive segment match (`storage` vs `Storage`).
- Round-trip: `to_fs_path(to_stored_path(p))` lands under `MEDIA_ROOT`.
- Contract test: a mocked `/query` object response and a mocked alert detail carry `/storage/...` URL paths.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
```

Then live: run capture for one event (or re-ingest a stored video), confirm the new Mongo doc has relative paths; ask an object question in the web UI and confirm the highlighted image renders; open an alert detail and confirm its image renders.
