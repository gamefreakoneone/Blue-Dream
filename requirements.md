# Project Memoria Requirements

## Product Goal

Project Memoria is a memory-grounded, voice-enabled dementia assistant. Home cameras record short room events; the system turns them into durable memory records; the patient asks natural questions ("Where are my keys?", "What was I doing yesterday?") by text or voice and gets grounded answers; the agent proactively starts conversations when it matters (a hazard left behind, a geofence exit, a morning report, a due reminder); caregivers get trustworthy, derived context instead of raw surveillance.

The memory system is the product. It must:

- persist and accumulate experience across sessions,
- remember stable personal facts and preferences,
- practice timely forgetting of outdated routine information (cleanup, never erasure),
- recall the critical memories within a limited context window when answering.

## Hackathon Targets

The same codebase serves two submissions through a hot-swappable model-provider layer:

| Target | Deadline | Required tech | Provider config |
|---|---|---|---|
| Qwen Cloud hackathon — MemoryAgent track | July 20, 2026, 2pm PT | Qwen models on Qwen Cloud (DashScope); repo code file proving Alibaba Cloud API usage | `LLM_PROVIDER=qwen` |
| OpenAI Build Week — Apps for Your Life | July 21, 2026, 5pm PT | Built with Codex + GPT-5.6; session ID + dated commits for work done Jul 13–21 | `LLM_PROVIDER=openai` |

Third-party APIs are allowed in both hackathons (no exclusivity clauses; licensing compliance only). Each submission maximizes its required provider; Gemini remains a licensed perception fallback where noted.

## Core Requirements

- Preserve the existing retrieval architecture: ChromaDB finds semantically similar candidates; MongoDB is the single source of truth for full event records.
- One async LLM client speaking the OpenAI chat-completions protocol (to be built in spec 0003; does not exist in the current codebase); `LLM_PROVIDER=qwen|openai|ollama` switches the entire app's reasoning, vision, and embedding stack. Qwen is the working provider throughout the rebuild; the openai profile is exercised only in spec 0012; ollama is optional (not installed on the dev machine).
- All media paths stored in MongoDB as relative POSIX paths; API responses always return URL paths (`/storage/...`, `/capture/...`); legacy absolute paths normalized at read time.
- Durable conversation memory: chat sessions persisted in MongoDB with automatic summarization of older turns; survives backend restarts.
- Profile facts: stable personal facts (people, preferences, routines, medical, safety) extracted from chat, deduplicated, always injected into answer prompts.
- Reminders: patient-created timed reminders delivered through the proactive channel.
- Memory lifecycle: importance scoring at ingest; consolidation of old low-importance events into daily summaries; consolidated originals removed from the semantic index but kept in MongoDB; pinned memories exempt from all decay.
- Context-budgeted recall: candidates re-ranked by relevance × recency × importance, pinned items guaranteed, packed into a token budget; the response exposes which memories were used (`recall_debug`).
- Proactive channel: the agent initiates chat turns for safety warnings, geofence exits, morning reports, and due reminders via a polled endpoint — no push infrastructure required.
- Voice: server-side speech-to-text and text-to-speech endpoints with a mic button in the web UI; provider-backed with a browser Web Speech fallback.
- Patient-facing text never contains raw exception messages.
- The capture pipeline (cameras, YOLO fall detection, recording) keeps working on the local machine; it can optionally post finished events to a remote backend.

## Delivery Order

Work proceeds one spec at a time under `docs/specs/`:

1. **0001 cleanup-and-hardening** — dead-code purge, dependency pinning, correctness fixes, test scaffold.
2. **0002 media-path-service** — the unified path convention.
3. **0003 llm-provider-layer** — the single OpenAI-protocol client, validated offline (first live validation in 0005 on Qwen).
4. **0004 capture-pipeline-fix** — camera_feed restructure and alert-service routing.
5. **0005 qwen-provider** — DashScope verification spike, then Qwen text/vision/embeddings.
6. **0006 durable-memory** — persistent conversations, profile facts, reminders.
7. **0007 memory-lifecycle** — importance, consolidation, pinning, budgeted recall.
8. **0008 proactive-channel** — trigger engine + agent-initiated chat.
9. **0009 voice-agent** — ASR/TTS endpoints + mic UI.
10. **0010 alibaba-deployment** (stretch) — Docker, `/ingest`, ECS walkthrough.
11. **0011 qwen-submission** — README, diagram, video, checklist.
12. **0012 openai-week** — GPT-5.6 flip, caregiver dashboard, submission package.

## Bar Raisers

- **Morning report**: on the patient's first camera sighting of the day, the agent opens the conversation with yesterday's summary and today's reminders.
- **Recall debug panel**: the web UI shows exactly which memories were packed into an answer — visible memory mechanics for judges and caregivers.

## Non-Goals (Current Scope)

- No facial recognition (post-hackathon backlog).
- No mobile push delivery; the Expo app stays in the repo untouched and demos are web-only.
- No Telegram/SMS caregiver channels (email path remains; backlog).
- No full `src/` package restructure (post-hackathon backlog).
- No user accounts, auth hardening, or production deployment beyond the demo topology.
- No medical-device claims; Memoria is a functional prototype, not an emergency-response replacement.
