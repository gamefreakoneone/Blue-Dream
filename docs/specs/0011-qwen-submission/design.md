# 0011 Qwen Submission Design

## Contracts You Must Not Break

- No code changes in this spec beyond README/docs/diagram assets; the demo configuration is frozen once rehearsal passes. If rehearsal exposes a bug, fix it as a minimal patch, re-run the affected beat, and note it in `status.md`.

## README structure (rewrite of the root `README.md`)

1. Title + one-paragraph pitch (memory-grounded, voice-enabled dementia assistant; Qwen-powered).
2. "Built for the Qwen Cloud Hackathon — MemoryAgent track" with the four track bullets → four shipped mechanisms table.
3. Demo GIF/screenshots (reuse/refresh `Demo/` assets).
4. Architecture section: the new diagram + the five-layer summary from `TECHNICAL_DESIGN.md` (link, don't duplicate).
5. What runs on Qwen Cloud (explicit model list per capability) / what uses other services (Gemini fallback scope, honestly stated).
6. Alibaba Cloud usage: DashScope integration files; ECS deployment section + proof screenshot if 0010 landed.
7. Setup: prerequisites, `.env` (Qwen profile), run commands, docker-compose path if available. (Ollama may be mentioned only as an optional local profile — it is not required and was never validated in this rebuild; the README must not list it as a prerequisite.)
8. Significantly-updated-after-May-26 changelog: table of specs 0001–0009(/0010) with one-line descriptions, linking `docs/FEATURE_STATUS.md`.
9. Prototype boundaries (honest limitations; not a medical device).

## Diagram

Produce `Demo/memoria-architecture-qwen.png`. Boxes: Home (cameras → capture/YOLO → consolidator) | Memory (MongoDB truth store, Chroma per-provider index) | Qwen Cloud (qwen-plus/max routing+synthesis+judging, qwen-vl vision/grounding, text-embedding-v4, ASR/TTS) | Backend (FastAPI: query, proactive, voice, alerts, geofence) | Patient (web chat + voice + proactive bubbles). Draw the ECS boundary around Memory+Backend if deployed. Keep labels legible at README width.

## Video production notes

- Record at 1080p, narrated (rules require audio explaining the project); OBS or equivalent; keep every beat under its script budget from `requirements.md`.
- Pre-stage data: a week of events including one hazard clip, one consolidated mundane day, a pinned medication fact, a stored personal fact from a "previous session".
- Record beats separately and cut; total < 3:00 hard (Devpost rejects overruns as rule violations).
- Upload YouTube **public** (not unlisted — rules say publicly visible), title "Project Memoria — Qwen Cloud MemoryAgent Track".

## Devpost form content

Draft the text description in `docs/SUBMISSIONS.md` first (features/functionality, track, what's new since May 26, Alibaba proof links, testing notes for judges: "requires home cameras; the video demonstrates the live system; the repo runs against any webcam setup with the documented .env").

## Submission-day runbook (Jul 20)

1. Morning: full clean-start rehearsal; fix-or-cut any broken beat (cut order in `FEATURE_STATUS.md`).
2. Record + edit video; upload; verify public playback in an incognito window.
3. Repo: final README, diagram committed, license visible in About, repo set public; secret scrub-check (`git log --diff-filter=A --name-only | grep -iE "credential|token|secret|google-services"` sanity pass + confirm `.env`, `Storage/`, `Proof/`, `Mobile/google-services.json` untracked).
4. Tag `qwen-submission`.
5. Submit Devpost form; screenshot the confirmation.
6. Update `docs/SUBMISSIONS.md` + this spec's `status.md` + `FEATURE_STATUS.md`.
7. Target: submitted by 12:00 PT; hard deadline 14:00 PT.

## Validation

The "test" for this spec is the rehearsal + an independent read-through: someone (or a fresh agent context) follows the README setup section verbatim and flags any step that doesn't match reality.
