# 0010 Alibaba Deployment Requirements (STRETCH)

## Goal

Run the Memoria backend (FastAPI + MongoDB) on one Alibaba Cloud ECS instance via docker-compose, with the local capture machine posting finished events to it through a new authenticated ingestion endpoint. This strengthens the Qwen submission's "runs on Alibaba Cloud" story.

**This spec is explicitly skippable.** Eligibility is already satisfied: the hackathon's proof requirement is "a repo code file demonstrating use of Alibaba Cloud services and APIs," which the DashScope integration (`Blue_dream_agents/llm/client.py`, `scripts/dashscope_spike.py`) provides. If the schedule slips, skip this spec per the cut order in `docs/FEATURE_STATUS.md` and the demo runs fully local.

## Functional Requirements

### Containerization (useful even without ECS)

- `Dockerfile` at repo root: python slim base, install pinned requirements (CPU-only — the container runs the API, not YOLO capture), run `uvicorn Blue_dream_agents.api:app --host 0.0.0.0 --port 8000`.
- `docker-compose.yml`: `mongo:7` (named volume, internal network only — port 27017 NOT published) + `memoria-api` (port 8000 published, `Storage/` named volume, env from `.env`).
- `docker compose up` on any machine yields a working backend answering `/query` (given provider keys in `.env`).

### Ingestion endpoint

- `POST /ingest/event`: multipart — `event` (MemoryEvent JSON, `screenshot_path` empty) + optional `screenshot` (JPEG). Auth: `X-Ingest-Token` header matched against `INGEST_TOKEN` env; 401 without it; the endpoint is disabled (404) when `INGEST_TOKEN` is unset.
- The backend saves the screenshot to `Storage/screenshots/{event_id}.jpg`, sets the stored path, then reuses the consolidator's persistence tail: dedupe by `video_path`, Mongo insert, importance/safety data passthrough (already computed on the capture side), Chroma indexing, morning-report trigger.
- The local capture pipeline gains a remote mode: when `INGEST_URL` (+ `INGEST_TOKEN`) is set, the consolidator finishes its local analysis (Gemini/Qwen video, transcription, safety, importance) and POSTs the result + screenshot instead of writing to Mongo directly. Unset → exactly today's local behavior. Videos are never uploaded.

### ECS deployment (the beginner walkthrough lives in `docs/DEPLOYMENT_ALIBABA.md`)

- One ECS instance (2 vCPU / 4GB, Ubuntu 22.04), security group exposing only 22 (SSH, your IP) and 8000.
- Deploy = clone repo → write `.env` → `docker compose up -d`.
- End-to-end proof: local capture records an event → appears in the cloud Mongo → the web UI served from the ECS instance answers a memory question about it → screenshot renders from the cloud `/storage` mount.

## Technical Constraints

- The ingest client (capture side) uses httpx with a timeout + one retry; on failure it falls back to local Mongo if reachable, else logs and drops (documented demo-grade durability).
- No OSS bucket, no ACK/serverless, no domain/TLS (LAN-grade demo posture; note the plain-HTTP caveat).
- The event JSON must round-trip through `MemoryEvent` validation on the receiving side; reject invalid payloads with 422.

## Non-Requirements

- No auth beyond the ingest token; no user accounts.
- No capture/YOLO inside the container.
- No media replication beyond screenshots.

## Acceptance Criteria

- `docker compose up` locally: `/query` answers, UI loads, static mounts serve.
- Unauthenticated `/ingest/event` → 401; valid post → event in Mongo + screenshot saved + Chroma indexed; duplicate `video_path` post → deduped.
- On ECS: the full loop (local capture → cloud ingest → web UI answer with image) demonstrated and screenshotted for the README.
- pytest covers the ingest contract (auth, validation, dedupe, screenshot save) with the endpoint enabled via env.
