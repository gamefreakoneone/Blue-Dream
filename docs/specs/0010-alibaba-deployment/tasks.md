# 0010 Alibaba Deployment Tasks (STRETCH — skippable per cut order)

## Prerequisites

- [ ] Specs 0001–0008 completed; Alibaba Cloud account + ECS access ready.
- [ ] Docker Desktop locally for compose testing.

## Implementation Tasks

- [ ] Extract the consolidator persistence tail into `ingest_event(event, screenshot_bytes)` (shared by local mode and the endpoint).
- [ ] `POST /ingest/event` with `X-Ingest-Token` auth (constant-time compare), 404-when-unset, 422 validation, screenshot save via `media_paths`.
- [ ] Capture-side remote mode: `INGEST_URL`/`INGEST_TOKEN` posting with timeout + retry + local fallback; unset → unchanged local behavior.
- [ ] `Dockerfile` (API-only; split `requirements-api.txt` if capture deps break the slim build; verify api.py's import graph pulls no capture-only deps).
- [ ] `docker-compose.yml` (mongo internal-only, api on 8000, volumes, env_file).
- [ ] Write/finalize `docs/DEPLOYMENT_ALIBABA.md` beginner walkthrough.
- [ ] Document `INGEST_URL`, `INGEST_TOKEN` in `.env.example`.

## Tests

- [ ] `tests/test_ingest.py`: disabled/401/422/dedupe/screenshot-save/indexing-failure cases.
- [ ] Full suite passes.

## Manual Checks

- [ ] `docker compose up --build` locally: UI loads, `/query` answers, `/storage` serves.
- [ ] ECS instance deployed per the walkthrough; UI reachable at `http://<ecs-ip>:8000`.
- [ ] Local capture event with `INGEST_URL` set lands in cloud Mongo; memory question about it answers in the cloud UI with the screenshot rendering.
- [ ] Duplicate re-post deduped; unauthenticated post rejected.
- [ ] Proof screenshot (ECS console + running UI) saved for the README/submission.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
