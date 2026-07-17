# Alibaba Cloud Deployment Walkthrough

A beginner-level guide for running the Memoria backend (FastAPI + MongoDB) on one Alibaba Cloud ECS instance. Companion to spec `docs/specs/0010-alibaba-deployment/`.

**You do not need this for hackathon eligibility.** The rules' proof requirement — a repo code file demonstrating Alibaba Cloud API usage — is already satisfied by the DashScope integration (`Blue_dream_agents/llm/client.py`, `scripts/dashscope_spike.py`). This deployment makes the story stronger, not eligible.

## What you are building

```
[Home PC: cameras + capture pipeline]  --HTTPS/HTTP POST /ingest/event-->  [ECS instance]
                                                                            ├─ Docker: memoria-api (FastAPI, port 8000)
                                                                            └─ Docker: mongo:7 (internal only)
Patient browser  ------------------------------ http://<ecs-ip>:8000 -----> web UI + memories
```

Cameras and video analysis stay at home. Only the finished memory record (JSON) plus one screenshot travel to the cloud. Videos never leave the house.

## Step 1 — Create the ECS instance (~10 min)

1. Log in to the Alibaba Cloud console → **Elastic Compute Service (ECS)** → Create Instance.
2. Choose: **Pay-as-you-go**, a region near you, instance type **2 vCPU / 4 GiB** (e.g. `ecs.e-c1m2.large` or similar economy type), image **Ubuntu 22.04 64-bit**, 40 GB system disk.
3. Networking: assign a **public IP** (default VPC is fine), bandwidth pay-by-traffic ~5 Mbps.
4. Security group — allow inbound:
   - TCP 22 (SSH) — restrict source to *your* IP if possible.
   - TCP 8000 (the API/UI).
   - Do **NOT** open 27017 (MongoDB stays internal to Docker).
5. Set a key pair (download the `.pem`) or a root password. Create the instance and note its **public IP**.

## Step 2 — Install Docker (~5 min)

SSH in (PowerShell works):

```powershell
ssh -i path\to\key.pem root@<ecs-public-ip>
```

Then on the server:

```bash
apt-get update && apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

## Step 3 — Get the code and configure (~5 min)

```bash
git clone <your-repo-url> memoria && cd memoria
cp .env.example .env
nano .env
```

Minimum `.env` for the cloud box:

```ini
LLM_PROVIDER=qwen
EMBEDDING_PROVIDER=qwen
TRANSCRIBE_PROVIDER=qwen
DASHSCOPE_API_KEY=<your key>
DASHSCOPE_BASE_URL=<the base URL confirmed in the spec 0005 spike>
GEMINI_API_KEY=<optional, perception fallback>
INGEST_TOKEN=<a long random string — same value goes on the home PC>
TIMEZONE=America/Los_Angeles
# MONGODB_URI is set by docker-compose to the internal mongo container
```

## Step 4 — Launch (~2 min)

```bash
docker compose up -d --build
docker compose ps          # both containers Up
curl -s localhost:8000/geofence/current   # sanity: JSON reply
```

Open `http://<ecs-public-ip>:8000` in a browser — the Memoria chat UI should load.

## Step 5 — Point the home capture pipeline at the cloud

On the home PC's `.env`:

```ini
INGEST_URL=http://<ecs-public-ip>:8000
INGEST_TOKEN=<same random string>
```

Restart the capture pipeline. The next recorded event is analyzed locally, then posted to the cloud. Verify:

```bash
# on the ECS box
docker compose exec mongo mongosh dementia_assistance --eval "db.events.countDocuments()"
```

Then ask the cloud UI a question about the event and confirm the screenshot renders.

## Step 6 — Capture the proof for the submission

- Screenshot: ECS console showing the running instance + the browser showing the Memoria UI at the public IP answering a memory question.
- Commit nothing secret; the proof screenshot goes in `Demo/` and is referenced from the README's Alibaba section.

## Troubleshooting

| Symptom | Check |
|---|---|
| UI unreachable | Security group rule for 8000; `docker compose ps`; `docker compose logs api` |
| `/ingest/event` 404 | `INGEST_TOKEN` not set in the server `.env` (endpoint is disabled without it) |
| `/ingest/event` 401 | Token mismatch between home PC and server |
| Semantic queries "insufficient evidence" | `DASHSCOPE_API_KEY`/base URL wrong — check `docker compose logs api` for embedding errors |
| Images 404 in UI | Event predates cloud ingestion (its screenshot lives only on the home PC) — expected for old events |

## Cost and teardown

Pay-as-you-go at this size is roughly $15–25/month equivalent — covered by hackathon credits; billed per hour. After judging:

```bash
docker compose down   # keep data:  docker compose down --volumes  removes it
```

then release the instance in the ECS console to stop all charges.

## Security posture (demo-grade, stated honestly)

Plain HTTP, no user auth, one shared ingest token, `/storage` publicly readable on port 8000. Acceptable for a judged demo with synthetic/demo data; not for real patient data. Production would need TLS, authentication, and media access controls — listed in the README's prototype boundaries.
