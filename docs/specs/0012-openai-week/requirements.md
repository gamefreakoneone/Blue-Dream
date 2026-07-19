# 0012 OpenAI Week Requirements

## Goal

Flip the provider profile to GPT-5.6, ship the caregiver dashboard as this week's headline new feature, assemble the work-evidence package (session IDs + dated commits), and submit to OpenAI Build Week ("Apps for Your Life") by **July 21, 2026, 5pm PT** (target: ~3pm PT).

## Submission Rules Recap

- Built with Codex and GPT-5.6; pre-existing projects judged **only on new work done July 13–21**, documented with a Codex session ID (the thread where the majority of core functionality was built) and dated commits.
- Demo video < 3 min, public YouTube, with audio explaining what was built and how Codex/GPT-5.6 were used.
- README must describe the Codex collaboration and key decisions.
- Repo public, or private and shared with testing@devpost.com and build-week-event@openai.com.

The new-work narrative: **everything in specs 0001–0012** was implemented during the submission window — the provider layer, the entire memory system, proactive channel, voice, deployment, and this spec's dashboard — with the dashboard + GPT-5.6 integration as the headline items built at the end of the week.

## Functional Requirements

### GPT-5.6 provider profile

- `LLM_PROVIDER=openai` runs the full app on GPT-5.6: routing, synthesis, judging, vision presence checks; embeddings on `text-embedding-3-small` (1536d sibling Chroma collection); voice on `gpt-4o-transcribe` / `gpt-4o-mini-tts`.
- Complete the `supports_json_schema` branch in `client.invoke_structured`: strict structured outputs via `response_format={"type":"json_schema", "json_schema": {..., "strict": true, "schema": output_model.model_json_schema()}}`; skip the schema-in-prompt text on this branch; hardening still wraps the result.
- Verify the exact current model id and structured-outputs parameter shape against the OpenAI docs at implementation time; record in `status.md`.

### Caregiver dashboard (`UI/dashboard.html` + `UI/dashboard.js`)

- A separate static page at `/dashboard.html` (served by the existing UI mount), clearly labeled "Caregiver view".
- Sections:
  1. **Patient profile facts** — list with category badges, pin/archive buttons (existing 0006 endpoints).
  2. **Daily summaries** — `memory_summaries` timeline (new `GET /memory/summaries?days=7`), plus a "Run memory cleanup" button (`POST /memory/consolidate`) showing the report.
  3. **Alerts** — recent `safety_alerts` including caretaker-targeted fall alerts (new `GET /alerts/recent?limit=20` returning all target roles), severity/status badges, highlighted images.
  4. **Reminders** — active list + create form (existing 0006 endpoints).
- Privacy framing visible on the page: the caregiver sees derived summaries, alerts, and facts — never raw video or audio.

### Submission package

- README gains an OpenAI Build Week section: what was built this week with Codex + GPT-5.6, key decisions, and the session-evidence pointer.
- `docs/SUBMISSIONS.md` OpenAI section: the Codex session ID(s), the dated-commit table (spec → commits, from `git log`), video URL, form contents.
- Demo video (<3 min): the dashboard + GPT-5.6-powered flows + the strongest memory beats, narrated with explicit "built with Codex / runs on GPT-5.6" framing.
- Tag `openai-submission`.

## Technical Constraints

- The Qwen submission state must remain reproducible: provider flips are env-only; no Qwen-path code may break (run the contract suite on both profiles).
- New endpoints (`/memory/summaries`, `/alerts/recent`) are JSON-safe and read-only.
- Dashboard is plain HTML/JS/CSS matching the existing UI stack — no build tooling.

## Non-Requirements

- No auth on the dashboard (LAN demo posture; stated on the page and in README).
- No caregiver editing of memories beyond pin/archive.
- No new mobile work.

## Acceptance Criteria

- Contract tests pass under provider-mocked config; live smoke on GPT-5.6 answers all four query types (this spec is the only place the openai profile is exercised live); structured calls use the json_schema branch (verified by request inspection in tests).
- Dashboard renders all four sections against real data; pin/archive/consolidate actions work.
- Video public, <3:00, explicitly demonstrates Codex/GPT-5.6 usage; submission confirmed before 5pm PT July 21 (target 3pm).
- `openai-submission` tag; `docs/SUBMISSIONS.md` complete.
