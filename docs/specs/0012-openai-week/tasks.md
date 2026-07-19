# 0012 OpenAI Week Tasks

## Prerequisites

- [ ] Qwen submission (0011) done and tagged; `OPENAI_API_KEY` in `.env`.

## Implementation Tasks

- [ ] Verify live GPT-5.6 model id + structured-outputs parameter shape against current OpenAI docs; record in `status.md`.
- [ ] Implement the `json_schema` strict branch in `invoke_structured` (+ additionalProperties post-processing, error fallback).
- [ ] Confirm/wire openai presets: text/vision GPT-5.6, `text-embedding-3-small`, `gpt-4o-transcribe`, `gpt-4o-mini-tts`.
- [ ] Add `GET /memory/summaries` and `GET /alerts/recent` (JSON-safe, read-only).
- [ ] Build `UI/dashboard.html` + `dashboard.js` (+ small css): profile facts w/ pin+archive, daily summaries + consolidation button w/ inline report, alerts (all roles) w/ images, reminders list/create; privacy line; auto-refresh.
- [ ] Voice round-trip smoke on the OpenAI profile.
- [ ] README "Built during OpenAI Build Week" section (Codex collaboration, key decisions, evidence pointers).
- [ ] `docs/SUBMISSIONS.md` OpenAI section: session ID(s), dated-commit table, video URL, form text.

## Tests

- [ ] json_schema branch request-shape + fallback tests (mocked SDK).
- [ ] New endpoint contract tests.
- [ ] Full suite green; contract suite run under both provider configs (openai mocked).

## Manual Checks

- [ ] Live GPT-5.6: all four query types answer; structured calls verified on the json_schema branch.
- [ ] Dashboard: all four sections render real data; pin/archive/consolidate all work; consolidation report displays.
- [ ] Qwen profile still works after all changes (env flip smoke).
- [ ] Video <3:00, public, narrated with explicit Codex/GPT-5.6 framing.
- [ ] Submission confirmed before 5pm PT July 21 (target 3pm); `openai-submission` tag pushed.

## Wrap-Up

- [ ] Update `docs/SUBMISSIONS.md`, `docs/FEATURE_STATUS.md`, and `status.md`; final commit.
