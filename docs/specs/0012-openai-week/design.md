# 0012 OpenAI Week Design

## Contracts You Must Not Break

- The Qwen submission configuration (tagged `qwen-submission`) must keep working — provider differences are config + the json_schema branch only.
- All existing endpoint contracts; the dashboard only adds read-only endpoints plus existing mutation endpoints.

## GPT-5.6 branch (`llm/client.py`)

In `invoke_structured`, when the resolved target has `supports_json_schema`:

```python
response_format = {
  "type": "json_schema",
  "json_schema": {
    "name": output_model.__name__,
    "strict": True,
    "schema": output_model.model_json_schema(),
  },
}
```

- Omit the schema-in-prompt instruction block on this branch (the API enforces the schema).
- Pydantic `model_json_schema()` output may need `additionalProperties: false` injected per object for strict mode — handle via a small schema-post-processing helper; verify against current OpenAI docs and note findings in `status.md`.
- Hardening still wraps parsing (belt and suspenders); the strict retry falls back to the json_object-style path if the schema request itself errors.
- `openai` presets in `model_registry`: confirm the live model id for GPT-5.6 and set `supports_json_schema=True` for it; embeddings `text-embedding-3-small` (1536) → sibling collection `memory_events__openai__text-embedding-3-small__1536` rebuilds automatically on first semantic query.

## New read endpoints (`api.py`)

```
GET /memory/summaries?days=7   -> {"summaries": [{summary_id, date, room_name, text, source_event_count}]}
GET /alerts/recent?limit=20    -> {"alerts": [...all target roles, JSON-safe, newest first]}
```

Follow the existing alert serialization helpers; no ObjectId leakage.

## Dashboard (`UI/dashboard.html`, `UI/dashboard.js`, reuse `UI/styles.css` + a small `dashboard.css`)

- Header: "Memoria — Caregiver view" + the privacy line ("Derived summaries, alerts, and facts only. No raw video or audio.") + link back to the patient chat.
- Five sections per requirements; each section = fetch → render → action buttons wired to existing/new endpoints; `escapeHtml` everything (copy the helper from `script.js`).
- Consolidation button shows the returned report inline (groups formed, events consolidated) — this doubles as a live demo of the memory-hygiene story.
- Auto-refresh alerts/summaries every 30s; manual refresh buttons elsewhere. Desktop-optimized.

## Voice on the OpenAI profile

`TTS_PROVIDER=openai` / `TRANSCRIBE_PROVIDER=openai` already exist as branches (0003/0009): confirm `gpt-4o-mini-tts` + `gpt-4o-transcribe` model names live, wire any missing param, smoke one round-trip.

## Evidence assembly (`docs/SUBMISSIONS.md` OpenAI section)

- Record the implementation-session ID(s) as required by the rules (the thread where core functionality was built) — log them as work proceeds, not retroactively.
- Dated-commit table: `git log --pretty="%h %ad %s" --date=short` grouped by spec; the whole 0001→0012 window is in-period new work.
- README "Built during OpenAI Build Week" section: what was built with Codex + GPT-5.6, key decisions (provider abstraction, memory lifecycle design, json_schema adoption), evidence pointers.

## Video (<3 min) outline

1. 0:00–0:20 — recap the product in two sentences; "rebuilt this week with Codex on GPT-5.6".
2. 0:20–1:10 — patient side on GPT-5.6: voice question → grounded answer; proactive hazard warning; morning report.
3. 1:10–2:10 — caregiver dashboard walkthrough: facts (pin), daily summaries, live consolidation run, alerts with images, geofence update.
4. 2:10–2:50 — how it was built: Codex workflow, spec ledger on screen, GPT-5.6 structured outputs + embeddings; architecture flash.
5. Close.

## Submission-day runbook (Jul 21)

1. Morning: finish dashboard; both-profile contract runs; GPT-5.6 live smoke.
2. Rehearse beats → record → upload public YouTube → incognito check.
3. README section + `docs/SUBMISSIONS.md` complete; tag `openai-submission`.
4. Submit Devpost form (repo public; if private instead, share with testing@devpost.com and build-week-event@openai.com); screenshot confirmation.
5. Update ledger + status. Target 15:00 PT; hard deadline 17:00 PT.

## Tests

- `tests/test_llm_client_json.py` additions: json_schema branch request shape (mocked SDK — assert `response_format` payload), strict-schema post-processing, fallback on schema-request error.
- Endpoint tests for `/memory/summaries` and `/alerts/recent`.
- Full suite green under default config.
