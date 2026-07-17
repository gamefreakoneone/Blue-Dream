# Hackathon Submissions Tracker

Both submissions ship from this one repository; only the provider profile and the narrative differ. Fill the evidence fields as work completes — this file is the working checklist for specs 0011 and 0012.

---

## 1. Qwen Cloud Hackathon — MemoryAgent Track

- **Deadline:** July 20, 2026, 2:00 pm PT (internal target: submitted by 12:00 pm PT)
- **Provider profile:** `LLM_PROVIDER=qwen`, `EMBEDDING_PROVIDER=qwen`, `TRANSCRIBE_PROVIDER=qwen` (+ `SPATIAL_PROVIDER`/`VIDEO_PROVIDER=qwen` if the 0005 stretch landed)

### Requirements checklist

- [ ] Uses Qwen models on Qwen Cloud; fits the MemoryAgent track.
- [ ] Provider profile flipped for the demo/video: `LLM_PROVIDER=qwen`, `EMBEDDING_PROVIDER=qwen`, **`TRANSCRIBE_PROVIDER=qwen`** (spec 0003's default stays `openai` — this must be set explicitly in `.env`).
- [ ] Public repo with open-source license file, visible in the About section.
- [ ] Text description of features and functionality.
- [ ] Alibaba Cloud proof link: `Blue_dream_agents/llm/client.py` + `scripts/dashscope_spike.py` (+ ECS evidence if 0010 landed).
- [ ] Architecture diagram (`Demo/memoria-architecture-qwen.png`).
- [ ] Demo video < 3:00, public YouTube, shows the working project.
- [ ] Pre-existing project: "significantly updated after May 26" explanation (spec ledger + dated commits).
- [ ] English materials.
- [ ] Optional: public blog/social post (bonus prize).

### Track story (for the form)

The four judged memory capabilities → shipped mechanisms:

| Track requirement | Mechanism |
|---|---|
| Persistent memory accumulating experience | MongoDB-backed conversation sessions + event memory (spec 0006) |
| Remembers user preferences | Profile-facts store, always injected into answers (spec 0006) |
| Timely forgetting of outdated information | Importance scoring + consolidation of stale routine events into daily summaries — archived, never erased (spec 0007) |
| Recalling critical memories in limited context | Relevance × recency × importance packing into a token budget, pinned memories guaranteed, visible `recall_debug` (spec 0007) |

Judge testing note: the system requires home cameras; the video demonstrates the live system; the repo runs against any webcam setup with the documented `.env`.

### Evidence (fill at submission)

- Repo URL / tag: `qwen-submission` @ `<commit>`
- Video URL:
- Devpost confirmation screenshot:
- Form text (copy):

---

## 2. OpenAI Build Week — Apps for Your Life

- **Deadline:** July 21, 2026, 5:00 pm PT (internal target: submitted by 3:00 pm PT)
- **Provider profile:** `LLM_PROVIDER=openai` (GPT-5.6), `EMBEDDING_PROVIDER=openai`, voice on OpenAI audio models
- **Optional credits:** the $100 OpenAI credit request closes **July 17, 2026, 12:00 pm PT** (use-by July 21, 5pm PT). Keys are already in hand; request only if extra credit is wanted.

### Requirements checklist

- [ ] Built with Codex and GPT-5.6; category: Apps for Your Life (health).
- [ ] Repo public (or private + shared with testing@devpost.com and build-week-event@openai.com).
- [ ] README describes the Codex collaboration and key decisions.
- [ ] Codex session ID for the thread where the majority of core functionality was built.
- [ ] Pre-existing project: new-vs-old work documented with dated commits (the entire spec 0001–0012 window is in-period).
- [ ] Demo video < 3:00, public YouTube, audio explains what was built and how Codex/GPT-5.6 were used.
- [ ] English materials.

### New-work narrative (for the form)

Rebuilt during the submission window with Codex: unified media-path system, single GPT-5.6-capable provider layer with strict structured outputs, durable cross-session memory, profile facts + reminders, memory lifecycle (importance, consolidation, pinning) with context-budgeted recall, proactive agent-initiated conversations, server-side voice, and the caregiver dashboard (headline feature, spec 0012). Judged-on-new-work evidence: dated commit table below + session IDs.

### Evidence (fill as work proceeds — not retroactively)

- Codex session ID(s):
- Dated-commit table (spec → commits): generate with `git log --pretty="%h %ad %s" --date=short`
- Repo URL / tag: `openai-submission` @ `<commit>`
- Video URL:
- Devpost confirmation screenshot:
- Form text (copy):

---

## Video scripts

Detailed beat-by-beat scripts live in the submission specs: `docs/specs/0011-qwen-submission/requirements.md` (Qwen) and `docs/specs/0012-openai-week/design.md` (OpenAI). Rehearse from a clean start before recording; hard cap 3:00 per rules.

## Shared pre-flight (both submissions)

- [ ] Secret scrub: `.env`, `Storage/`, `Proof/`, `Mobile/google-services.json`, Gmail tokens all untracked; no keys in tracked files.
- [ ] LICENSE file present and shown in the repo About section.
- [ ] Fresh-clone README setup test passed.
- [ ] `docs/FEATURE_STATUS.md` current — it is part of the judged documentation story.
