# 0011 Qwen Submission Requirements

## Goal

Package and submit the Qwen Cloud MemoryAgent entry by **July 20, 2026, 2pm PT** (target: submitted by ~noon PT with buffer). Everything the judges see — README, architecture diagram, demo video, Devpost form — is produced by this spec.

## Submission Checklist (from the official rules)

- [ ] Project uses Qwen models on Qwen Cloud and fits the MemoryAgent track.
- [ ] **Public** repository with an open-source license file, visible in the repo About section.
- [ ] Text description of features and functionality (Devpost form).
- [ ] **Proof of Alibaba Cloud usage**: a link to a repo code file demonstrating Alibaba Cloud services/APIs — link `Blue_dream_agents/llm/client.py` (DashScope integration), `Blue_dream_agents/oss_media.py` (Alibaba OSS video bridge), and `scripts/dashscope_spike.py` (exercises both); plus the ECS deployment evidence if spec 0010 landed. Two Alibaba services (Model Studio + OSS) strengthen the story.
- [ ] **Architecture diagram** showing how Qwen Cloud connects to backend, database, and frontend.
- [ ] **Demo video under 3 minutes**, publicly hosted (YouTube), showing the project working.
- [ ] Track identification: MemoryAgent.
- [ ] Pre-existing-project explanation: what was significantly updated after May 26 (the provider layer, the entire memory system — durable conversations, profile facts, lifecycle/consolidation, budgeted recall — proactive channel, voice, deployment; point at the dated commit history and `docs/FEATURE_STATUS.md`).
- [ ] Optional: public blog/social post for the bonus prize.

## Functional Requirements

### README rewrite

- Honest architecture statement: Qwen (via Qwen Cloud/DashScope) owns routing, synthesis, evidence judging, vision presence checks, embeddings, ASR, and video understanding (recordings uploaded to Alibaba OSS, consumed by presigned URL) — plus grounding where the 0005 stretch landed; Gemini remains a perception fallback where configured; nothing overclaims.
- The MemoryAgent story front and center: the four track bullets mapped to the four shipped mechanisms (persistence → durable memory; preferences → profile facts; timely forgetting → lifecycle/consolidation with the "memory hygiene, never erasure" framing; limited-context recall → budgeted packing with `recall_debug`).
- Setup instructions that actually match the runtime (fresh-clone tested), the Qwen provider profile, and the demo flow.
- The "significantly updated after May 26" section with the spec ledger and commit anchors.

### Architecture diagram

- One clean image (draw.io/Excalidraw → PNG committed under `Demo/`): cameras → capture → ingestion → MongoDB/Chroma → Qwen Cloud (models labeled) → FastAPI → web UI (chat/voice/proactive); include the OSS bucket on the ingestion→Qwen video path; ECS boundary drawn if 0010 landed.

### Demo video (<3 min, YouTube public)

Script (adjust to what actually demos best; rehearse from a clean start first):

1. 0:00–0:25 — the problem: dementia, lost context, caregiver burden.
2. 0:25–0:55 — grounded recall: spoken "where is my water bottle?" → highlighted image answer; "what was I doing yesterday?" → timeline.
3. 0:55–1:25 — memory that persists: personal fact from a previous session used in a fresh session; backend restart mid-conversation survives.
4. 1:25–2:00 — memory hygiene: consolidation collapses a mundane day; pinned medication memory recalled from a week ago; the "Memory used" panel showing recency/importance ranking.
5. 2:00–2:30 — the agent speaks first: hazard warning bubble with highlighted image; event-triggered reminder ("don't forget your water bottle" as the patient is seen leaving for a walk); morning report.
6. 2:30–3:00 — architecture slide: Qwen end-to-end (models named), MongoDB + Chroma, Alibaba Cloud; close on the mission.

### Final rehearsal

- One complete run-through from a clean start (capture → ingest → all demo beats) on the exact demo configuration before recording.

## Technical Constraints

- Repo must be public **before** submission; scrub-check: no secrets, no `google-services.json`, no tokens in history being newly exposed (the repo history already exists — verify `.gitignore`d artifacts stayed out).
- All submission materials in English.
- The video shows real behavior — no mockups presented as working features.

## Non-Requirements

- No mobile demo. No live judge-accessible hosted instance promised (note in the description that the system requires home cameras; the video is the demonstration).

## Acceptance Criteria

- Devpost submission confirmed before the deadline with all checklist items attached.
- `docs/SUBMISSIONS.md` updated with the submitted links (repo state/tag, video URL, form contents copy).
- A `qwen-submission` git tag on the submitted commit.
