# Feature Status

Use this as the quick project ledger before opening individual spec folders. Detailed requirements, designs, tasks, and evidence live under each `docs/specs/NNNN-feature-name/` folder.

Two hard deadlines govern sequencing: **Qwen Cloud submission July 20, 2026, 2pm PT** (specs 0001–0011) and **OpenAI Build Week submission July 21, 2026, 5pm PT** (spec 0012).

| Spec | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| 0001 | Cleanup And Hardening | Completed | `docs/specs/0001-cleanup-and-hardening/status.md` | 23 offline tests pass; pinned deps, safe errors, timeout, lifespan, alert init, and cleanup completed in this commit. |
| 0002 | Media Path Service | In progress | `docs/specs/0002-media-path-service/status.md` | Implementation complete and 34 tests pass. Live ingestion/object validation now points to the spec 0005 Qwen ASR/reasoning gate; no image-bearing alert exists for the final render check. |
| 0003 | LLM Provider Layer | Completed | `docs/specs/0003-llm-provider-layer/status.md` | Unified async client, direct consumer migration, provider-specific Chroma collections, and FastAPI client-cache cleanup; 49 offline tests pass. First live model validation remains in 0005 on Qwen. |
| 0004 | Capture Pipeline Fix | Completed | `docs/specs/0004-capture-pipeline-fix/status.md` | Commit `653a652`; per-camera capture/state refactor, CWD-independent config, async caretaker fall alerts; 68 tests pass and one-camera live capture verified. Qwen/OSS understanding remains in 0005. |
| 0005 | Qwen Provider | Completed | `docs/specs/0005-qwen-provider/status.md` | Commit `73de261`; 74 tests and the 9/9 live DashScope/OSS spike pass. User-run textual routes worked, Qwen Chroma contains 42 records beside the preserved 40-record legacy collection, and genuine event `6a5bfb30d5533af854270f0a` persisted its transcript, video description, and canonical OSS key. Video ladder: OSS-URL Qwen → full-video Gemini → partial event, with no frame sampling. |
| 0006 | Durable Memory | Completed | `docs/specs/0006-durable-memory/status.md` | Commit `42978c3`; 87 tests plus isolated live Qwen/API restart rehearsal pass. Mongo-backed conversations, deduplicated profile facts, and time/event reminders are durable. |
| 0007 | Memory Lifecycle | Completed | `docs/specs/0007-memory-lifecycle/status.md` | Commit `d0c80c9`; 103 tests plus isolated live Qwen consolidation/recall and desktop/mobile Chrome rendering pass. Memory hygiene consolidates and archives source events, never erases them. |
| 0008 | Proactive Channel | Not started | `docs/specs/0008-proactive-channel/status.md` | Trigger engine (safety, morning report, time + event-triggered reminders) + polled agent-initiated chat. Geofence check-ins descoped to backlog. |
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

1. Video understanding degrades down its ladder: OSS-URL Qwen analysis → full-video Gemini fallback → partial event. Frame sampling is intentionally excluded for long recordings. Qwen-VL grounding (core in 0005) is the first cut lever — if the schedule slips it degrades to the Gemini fallback.
2. Spec 0010 ECS deployment is skipped entirely (DashScope usage in code is sufficient proof).
3. Voice degrades from DashScope ASR/TTS to the browser Web Speech API (fallback tasks in 0009).
4. Event-triggered reminders degrade to schema-only (0006 keeps the `trigger_type` field; the 0008 matcher is dropped); the demo uses time-based reminders.

## Post-Hackathon Backlog

Full `src/` package restructure; facial recognition; mobile push delivery fix (provider mismatch, geofence screen, SDK-54 notification triggers); geofence proactive check-ins (exit detection → check-in message + route-home action); Telegram/SMS caregiver channel.

## Update Rule

When a feature changes status, update this file and the matching spec folder status/task files in the same change. Record commit hashes and work-session identifiers in the Notes column as evidence for the hackathon submissions.
