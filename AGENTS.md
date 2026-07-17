# Repository Guidelines

## Project Purpose

Project Memoria is a memory-grounded, voice-enabled dementia assistant. Home cameras record short room events; the backend turns them into durable memory records in MongoDB; the patient asks questions by text or voice and gets grounded answers; the agent proactively starts conversations for safety warnings, geofence exits, morning reports, and reminders; caregivers see derived context, not raw surveillance.

The project targets two hackathon submissions from one codebase via a hot-swappable provider layer: Qwen Cloud (MemoryAgent track, due July 20, 2026, 2pm PT, `LLM_PROVIDER=qwen`) and OpenAI Build Week (Apps for Your Life, due July 21, 2026, 5pm PT, `LLM_PROVIDER=openai`).

`docs/archive/` holds the pre-rebuild AGENTS/PLANS baselines. They are historical reference, not the implementation base.

## Working Rules

- Check `docs/FEATURE_STATUS.md` before starting work to see completed specs, the current target, and verification evidence.
- Work one spec at a time, in numeric order, from `docs/specs/NNNN-feature-name/`. Read the spec's `requirements.md`, `design.md`, and `tasks.md` fully before coding.
- When a spec's status changes, update `docs/FEATURE_STATUS.md` and that spec's `status.md` (and `tasks.md` checkboxes) in the same change.
- Validate before committing: run the validation steps listed in the spec's `tasks.md` and record the evidence in `status.md`.
- Commit each completed spec separately with a descriptive message. Dated commits are part of the hackathon submission evidence.
- Keep `README.md` current: when run/setup steps, commands, prerequisites, or env vars change, update `README.md` in the same change.
- Preserve the stable contracts listed in `TECHNICAL_DESIGN.md` (Key Contracts) unless a spec explicitly migrates them.
- Do not put raw exception text in patient-facing responses. Log server-side; return a fixed reassuring message.
- MongoDB is the source of truth; ChromaDB must always be rebuildable from it. Never write smoke-test data into production collections.
- Never commit secrets, tokens, credential files, or service-account JSON. `.env` stays untracked; document new variables in `.env.example`.
- Treat `Storage/`, `Proof/`, and other gitignored media as runtime data, not source.
- Verify provider API behavior (DashScope, OpenAI) against current official docs before coding against it; spec 0005 begins with a mandatory verification spike.

## Development Environment

- Windows 11 + PowerShell is the primary environment.
- Python runs in the `Project-Memoria` conda environment (`conda activate Project-Memoria`). **Never run on base Python** — packages are only installed in `Project-Memoria`. Use it for all Python development and execution; when adding a dependency, pin it in `requirements.txt` in the same change.
- MongoDB runs locally by default (`MONGODB_URI` overrides).
- Default provider for the rebuild is `LLM_PROVIDER=qwen` (DashScope key in `.env` as `DASHSCOPE_API_KEY`, with `QWEN_APIKEY` accepted as a fallback name). The OpenAI profile is used only by spec 0012. Ollama is an optional local profile — **not installed on the dev machine**; never make it a prerequisite. The pre-rebuild `.env` runs Bedrock/Nova reasoning until spec 0003 replaces it.
- Backend: `uvicorn Blue_dream_agents.api:app --reload` (UI at `http://localhost:8000`).
- Capture: `python Capture/camera_feed.py`.
- Tests: `python -m pytest tests/` (the `tests/` scaffold is created by spec 0001; it does not exist before then).

## Project Areas

- `Blue_dream_agents/` — FastAPI backend, agents (routing, time, object, safety), memory stores, alert service, provider layer (`llm/`).
- `Capture/` — camera ingestion, fall detection, audio capture, video queue. Runs on the local machine with physical webcams.
- `UI/` — static patient web app served by FastAPI (chat, voice, proactive turns, emergency panel).
- `Mobile/` — prototype-stage Expo React Native app. Kept in the repo, not part of the current demo; do not spend effort here unless a spec says so.
- `docs/specs/` — per-feature requirements, design, tasks, and status.
- `docs/archive/` — pre-rebuild planning baselines (reference only).
- `tests/` — pytest suite (contract smokes, path service, provider JSON handling); scaffolded by spec 0001.

## Provider Architecture

Target architecture, built by specs 0003 (client) and 0005 (Qwen wiring) — before those specs complete, the legacy dispatch in `Blue_dream_agents/llm/strands_runtime.py`/`ollama_runtime.py` is what actually runs: one async client (`Blue_dream_agents/llm/client.py`, OpenAI SDK) serves text, structured output, vision, video frames, embeddings, ASR, and TTS. `LLM_PROVIDER=qwen|openai|ollama` selects the profile; per-capability env vars override pieces (`EMBEDDING_PROVIDER`, `VIDEO_PROVIDER`, `SPATIAL_PROVIDER`, `TRANSCRIBE_PROVIDER`, `TTS_PROVIDER`). Gemini remains a licensed fallback for video understanding and spatial grounding.

Each embedding provider/model gets its own Chroma collection (`memory_events__{provider}__{model_slug}__{dim}`); switching providers rebuilds from MongoDB and never destroys another provider's index.

See the provider table and env surface in `TECHNICAL_DESIGN.md`.

## Quality Bar

- Keep docs explicit enough for another agent or engineer to implement without guessing.
- Every spec ships with its validation evidence recorded in `status.md`.
- Structured LLM calls always go through the shared JSON-hardening path; never parse model output ad hoc.
- Prefer minimal targeted changes over cross-cutting rewrites; the full package restructure is explicitly post-hackathon backlog.
- Patient safety framing: memories are archived or consolidated, never erased; pinned safety-critical memories never decay.
