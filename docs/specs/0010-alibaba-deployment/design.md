# 0010 Alibaba Deployment Design (STRETCH)

## Contracts You Must Not Break

- Local-only operation stays the default: `INGEST_URL` unset → consolidator writes Mongo directly, exactly as today.
- Consolidator idempotency and failure isolation are preserved in the shared persistence tail.
- 27017 is never exposed publicly.

## Refactor: extract the persistence tail

`Blue_dream_agents/consolidator.py` currently ends with: dedupe check → Mongo insert → alert creation → Chroma indexing (→ 0008 morning-report trigger). Extract that tail into:

```python
async def ingest_event(event: MemoryEvent, screenshot_bytes: bytes | None = None) -> IngestResult
# IngestResult: {inserted: bool, deduped: bool, event_id, indexing_ok: bool}
```

in a new `Blue_dream_agents/ingest_service.py` (or within consolidator if cleaner — implementer's choice, but one function must own the tail). When `screenshot_bytes` is provided, save to `Storage/screenshots/{event_id}.jpg` via `media_paths` and set the stored path before insert.

## Endpoint (`api.py`)

```
POST /ingest/event   multipart: event=<MemoryEvent JSON string>, screenshot=<file, optional>
  401 when X-Ingest-Token missing/mismatched; 404 when INGEST_TOKEN unset
  422 on MemoryEvent validation failure
  200 -> IngestResult JSON
```

Constant-time token comparison (`secrets.compare_digest`). Size cap on the screenshot (~5MB).

## Capture-side remote mode

In the consolidator, after analysis completes:

```python
if settings.ingest_url:
    await post_to_ingest(event, screenshot_bytes)   # httpx, 30s timeout, 1 retry
    # on failure: try local Mongo if configured/reachable; else log-and-drop with a loud warning
else:
    await ingest_event(event, ...)                  # today's behavior
```

`INGEST_URL` (e.g. `http://<ecs-ip>:8000`) + `INGEST_TOKEN` in the capture machine's `.env`. The web UI on the capture machine is irrelevant in remote mode — the cloud instance serves the UI.

## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY Blue_dream_agents/ Blue_dream_agents/
COPY UI/ UI/
COPY Capture/__init__.py Capture/__init__.py   # package marker only; no capture code runs in-container
RUN mkdir -p Storage
EXPOSE 8000
CMD ["uvicorn", "Blue_dream_agents.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Check whether `requirements.txt` entries like `ultralytics`/`pyaudio`/`torch` break a slim build — if so, split a `requirements-api.txt` (API-only deps) used by the Dockerfile; the root file keeps the full local set. The API imports must not pull capture-only deps at module import time (verify; `api.py` shouldn't import ultralytics — if anything does transitively, fix the import placement).

## docker-compose.yml

```yaml
services:
  mongo:
    image: mongo:7
    volumes: [mongo_data:/data/db]
    # no ports: internal only
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    environment:
      - MONGODB_URI=mongodb://mongo:27017
    volumes: [storage_data:/app/Storage]
    depends_on: [mongo]
volumes: { mongo_data: {}, storage_data: {} }
```

## ECS walkthrough

Full beginner steps live in `docs/DEPLOYMENT_ALIBABA.md` (written alongside this spec): instance creation, security group, Docker install, clone, `.env`, `docker compose up -d`, verification URLs, and the README screenshot checklist.

## Tests (`tests/test_ingest.py`)

- Endpoint disabled without `INGEST_TOKEN` (404); wrong token 401; valid token + valid event 200 with insert; duplicate `video_path` → `deduped: true`, single Mongo doc; invalid event JSON 422; screenshot saved to the stored path and event's `screenshot_path` set (fake collection + tmp MEDIA_ROOT).
- `ingest_event` unit: with/without screenshot bytes; indexing failure still returns `inserted: true, indexing_ok: false`.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/test_ingest.py -q
docker compose up --build      # local: /query, UI, /storage all answer
```

Live on ECS: follow `docs/DEPLOYMENT_ALIBABA.md`; run one capture event on the local machine with `INGEST_URL` set; verify the event answers a memory question in the cloud-served UI with its screenshot; capture the proof screenshot for the README.
