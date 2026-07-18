# Feature Status

Use this as the quick project ledger before opening individual spec folders. Detailed requirements, designs, tasks, and evidence live under each `docs/specs/NNNN-feature-name/` folder.

Two hard deadlines govern sequencing: **Qwen Cloud submission July 20, 2026, 2pm PT** (specs 0001–0011) and **OpenAI Build Week submission July 21, 2026, 5pm PT** (spec 0012).

| Spec | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| 0001 | Cleanup And Hardening | Completed | `docs/specs/0001-cleanup-and-hardening/status.md` | 23 offline tests pass; pinned deps, safe errors, timeout, lifespan, alert init, and cleanup completed in this commit. |
| 0002 | Media Path Service | In progress | `docs/specs/0002-media-path-service/status.md` | Implementation complete and 34 tests pass. Live ingestion/object validation now points to the spec 0005 Qwen ASR/reasoning gate; no image-bearing alert exists for the final render check. |
| 0003 | LLM Provider Layer | Completed | `docs/specs/0003-llm-provider-layer/status.md` | Unified async client, direct consumer migration, provider-specific Chroma collections, and FastAPI client-cache cleanup; 49 offline tests pass. First live model validation remains in 0005 on Qwen. |
| 0004 | Capture Pipeline Fix | Completed | `docs/specs/0004-capture-pipeline-fix/status.md` | Commit `653a652`; per-camera capture/state refactor, CWD-independent config, async caretaker fall alerts; 68 tests pass and one-camera live capture verified. Qwen/OSS understanding remains in 0005. |
| 0005 | Qwen Provider | Not started | `docs/specs/0005-qwen-provider/status.md` | DashScope spike first (incl. OSS video round-trip); then Qwen text/structured/vision/embeddings + OSS-URL video understanding; VL grounding as stretch. **First live end-to-end gate** — Qwen is the only dev provider (Ollama not installed; openai used only in 0012). |
| 0006 | Durable Memory | Not started | `docs/specs/0006-durable-memory/status.md` | Mongo-backed conversations, profile facts, reminders. |
| 0007 | Memory Lifecycle | Not started | `docs/specs/0007-memory-lifecycle/status.md` | Importance at ingest, consolidation, pinning, context-budgeted recall, recall debug panel. |
| 0008 | Proactive Channel | Not started | `docs/specs/0008-proactive-channel/status.md` | Trigger engine (safety, geofence, morning report, reminders) + polled agent-initiated chat. |
| 0009 | Voice Agent | Not started | `docs/specs/0009-voice-agent/status.md` | Server-side ASR/TTS endpoints + mic UI; browser Web Speech fallback ladder. |
| 0010 | Alibaba Deployment (stretch) | Not started | `docs/specs/0010-alibaba-deployment/status.md` | Docker/compose, `/ingest/event`, beginner ECS walkthrough. Skippable: DashScope usage already satisfies proof. |
| 0011 | Qwen Submission | Not started | `docs/specs/0011-qwen-submission/status.md` | README rewrite, architecture diagram, <3min video, checklist. Submit by ~noon PT Jul 20. |
| 0012 | OpenAI Week | Not started | `docs/specs/0012-openai-week/status.md` | GPT-5.6 provider flip, caregiver dashboard, submission package. Submit by ~3pm PT Jul 21. |

## Status Definitions

- `Completed`: implemented and verified enough for the current project phase.
- `In progress`: implementation or verification is actively underway.
- `Blocked`: cannot proceed without a decision, dependency, credential, or external fix.
- `Not started`: spec exists, but implementation has not begun.

## Cut Order (if the schedule slips)

1. Video understanding degrades down its ladder: OSS-URL video → frame sampling → Gemini fallback; Qwen-VL grounding stays on the Gemini fallback (stretch task in 0005).
2. Spec 0010 ECS deployment is skipped entirely (DashScope usage in code is sufficient proof).
3. Voice degrades from DashScope ASR/TTS to the browser Web Speech API (fallback tasks in 0009).

## Post-Hackathon Backlog

Full `src/` package restructure; facial recognition; mobile push delivery fix (provider mismatch, geofence screen, SDK-54 notification triggers); Telegram/SMS caregiver channel.

## Update Rule

When a feature changes status, update this file and the matching spec folder status/task files in the same change. Record commit hashes and work-session identifiers in the Notes column as evidence for the hackathon submissions.
