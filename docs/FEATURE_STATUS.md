# Feature Status

Use this as the quick project ledger before opening individual spec folders. Detailed requirements, designs, tasks, and evidence live under each `docs/specs/NNNN-feature-name/` folder.

Two hard deadlines govern sequencing: **Qwen Cloud submission July 20, 2026, 2pm PT** (specs 0001–0008a, then **0013**, then 0011; 0009 voice is a stretch decided the morning of Jul 20) and **OpenAI Build Week submission July 21, 2026, 5pm PT** (spec 0012).

| Spec | Feature | Status | Evidence | Notes |
|---|---|---|---|---|
| 0001 | Cleanup And Hardening | Completed | `docs/specs/0001-cleanup-and-hardening/status.md` | 23 offline tests pass; pinned deps, safe errors, timeout, lifespan, alert init, and cleanup completed in this commit. |
| 0002 | Media Path Service | In progress | `docs/specs/0002-media-path-service/status.md` | Implementation complete and 34 tests pass. Live ingestion/object validation now points to the spec 0005 Qwen ASR/reasoning gate; no image-bearing alert exists for the final render check. |
| 0003 | LLM Provider Layer | Completed | `docs/specs/0003-llm-provider-layer/status.md` | Unified async client, direct consumer migration, provider-specific Chroma collections, and FastAPI client-cache cleanup; 49 offline tests pass. First live model validation remains in 0005 on Qwen. |
| 0004 | Capture Pipeline Fix | Completed | `docs/specs/0004-capture-pipeline-fix/status.md` | Commit `653a652`; per-camera capture/state refactor, CWD-independent config, async caretaker fall alerts; 68 tests pass and one-camera live capture verified. Qwen/OSS understanding remains in 0005. |
| 0005 | Qwen Provider | Completed | `docs/specs/0005-qwen-provider/status.md` | Commit `73de261`; 74 tests and the 9/9 live DashScope/OSS spike pass. User-run textual routes worked, Qwen Chroma contains 42 records beside the preserved 40-record legacy collection, and genuine event `6a5bfb30d5533af854270f0a` persisted its transcript, video description, and canonical OSS key. Video ladder: OSS-URL Qwen → full-video Gemini → partial event, with no frame sampling. |
| 0006 | Durable Memory | Completed | `docs/specs/0006-durable-memory/status.md` | Commit `42978c3`; 87 tests plus isolated live Qwen/API restart rehearsal pass. Mongo-backed conversations, deduplicated profile facts, and time/event reminders are durable. |
| 0007 | Memory Lifecycle | Completed | `docs/specs/0007-memory-lifecycle/status.md` | Implementation commit `d0c80c9` plus the completed course correction: 107 tests pass with zero failures/errors, the destructive rehearsal is guarded, non-subset consolidation is recoverable, and the isolated live Qwen rehearsal passes. Earlier non-reproducing pytest evidence is superseded in `status.md`; UI evidence remains independently verified. |
| 0008 | Proactive Channel | Completed | `docs/specs/0008-proactive-channel/status.md` | Commit `4456ff9`; 118 tests pass, and the isolated live Qwen/API plus rendered browser rehearsals verify all four triggers, expiry, global delivery, rollover, dedupe/re-arm, conversation append, and acknowledgement. Geofence behavior remains unchanged. |
| 0008a | Audit Cleanup | Completed | `docs/specs/0008a-audit-cleanup/status.md` | Implementation commit: this commit/`HEAD`; 129 tests pass with zero failures/errors. Isolated Qwen/API evidence verifies due-reminder answers and stored-to-URL proactive media conversion; capture startup remains functional. |
| 0009 | Voice Agent | Not started (stretch) | `docs/specs/0009-voice-agent/status.md` | Demoted behind 0013 on Jul 19; go/no-go decided the morning of Jul 20. Server-side ASR/TTS endpoints + mic UI; browser Web Speech fallback ladder. |
| 0010 | Alibaba Deployment (stretch) | Not started | `docs/specs/0010-alibaba-deployment/status.md` | Docker/compose, `/ingest/event`, beginner ECS walkthrough. Skippable: DashScope usage already satisfies proof. |
| 0011 | Qwen Submission | Not started | `docs/specs/0011-qwen-submission/status.md` | README rewrite, architecture diagram, <3min video, checklist. Submit by ~noon PT Jul 20. |
| 0012 | OpenAI Week | Not started | `docs/specs/0012-openai-week/status.md` | GPT-5.6 provider flip, caregiver dashboard, submission package. Submit by ~3pm PT Jul 21. `GET /memory/summaries` is delivered early by 0013. |
| 0013 | Web UI Rehaul | **Implemented — pending demo-morning phone validation** | `docs/specs/0013-web-ui-rehaul/status.md` | Phase commits `57c3bc7`, `adbff9f`, `e6e692b`, `20d5854`, `63ca813`. Implemented before 0009 with no cut lines exercised. Phone-only PWA install, closed-app push, notification tap, lock-screen, and adb checks remain explicitly pending; change to Completed only after that evidence is recorded. |
| 0013a | Course Correction | **Implemented — pending demo-morning phone validation** | `docs/specs/0013a-course-correction/status.md` | Phases A–D implemented and automatically validated: reminder intent/confirmation, list-only reminders with daily rollover/archive, safety-ack sync, top-bar new chat, and cached daily digest. Intentionally left uncommitted for on-device review; handset reminder, push-ack, and installed-PWA digest checks remain pending. |

## Status Definitions

- `Completed`: implemented and verified enough for the current project phase.
- `In progress`: implementation or verification is actively underway.
- `Blocked`: cannot proceed without a decision, dependency, credential, or external fix.
- `Not started`: spec exists, but implementation has not begun.

## Cut Order (if the schedule slips)

1. Video understanding degrades down its ladder: OSS-URL Qwen analysis → full-video Gemini fallback → partial event. Frame sampling is intentionally excluded for long recordings. Qwen-VL grounding (core in 0005) is the first cut lever — if the schedule slips it degrades to the Gemini fallback.
2. Spec 0010 ECS deployment is skipped entirely (DashScope usage in code is sufficient proof).
3. Voice (0009) is a stretch goal decided the morning of Jul 20; if attempted, it degrades from DashScope ASR/TTS to the browser Web Speech API (fallback tasks in 0009).
3a. Spec 0013 carries its own internal cut lines (see `docs/specs/0013-web-ui-rehaul/tasks.md`): summaries UI → event-reminder form → notification fallback/chime → Memories tab. The push chain, ChatScreen, Reminders, Safety, and PWA install are never cut.
4. Event-triggered reminders degrade to schema-only (0006 keeps the `trigger_type` field; the 0008 matcher is dropped); the demo uses time-based reminders.

## Post-Hackathon Backlog

Full `src/` package restructure; facial recognition; native mobile apps (the Expo prototype is deleted by spec 0013; web push replaces mobile push for the demo); geofence proactive check-ins (exit detection → check-in message + route-home action); Telegram/SMS caregiver channel.

## Update Rule

When a feature changes status, update this file and the matching spec folder status/task files in the same change. Record commit hashes and work-session identifiers in the Notes column as evidence for the hackathon submissions.
