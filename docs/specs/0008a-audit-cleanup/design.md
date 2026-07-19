# 0008a Audit Cleanup Design

Written July 19, 2026, from a three-track audit of specs 0001–0008 against `AGENTS.md`, `requirements.md`, and `TECHNICAL_DESIGN.md`. Read this together with `requirements.md` and `tasks.md` before changing anything.

## Audit context — what is already verified compliant (do not re-audit, do not rework)

- **Media paths (0002):** three-form path service, read-time legacy normalization, URL form at every API boundary, stored form on every Mongo write — verified across consolidator, capture, object detector, alert service.
- **Provider layer (0003/0005):** single `AsyncOpenAI` client; Qwen model table matches `TECHNICAL_DESIGN.md` exactly; structured-output hardening (fence strip, embedded-JSON extraction, Pydantic validation, one strict retry, `json_object` layering) on every structured call; per-provider Chroma collections; Gemini video fallback chain preserved; OSS bridge uploads at ingestion, never blocks ingestion, ladder OSS-URL Qwen → full-video Gemini → partial event with no frame sampling.
- **Durable memory (0006) and lifecycle (0007):** point-for-point compliant — conversations never embedded and never monitoring evidence; profile facts deduplicated and pinned-first; both reminder kinds with `origin_context`; consolidation removes from Chroma only, zero deletes on `events` in production code; recall formula exactly `similarity × exp(-age_days/half_life) × (1 + importance)` with pinned guarantees and `recall_debug`; destructive rehearsal scripts guarded.
- **Capture (0004) and proactive (0008):** tuned values env-tunable with correct defaults; once-per-recording fall guard; end-of-event screenshot; all four proactive triggers with race-safe dedupe (unique partial index on `related_id`), atomic delivery, expiry, daily re-arm, `EVENT_REMINDER_LLM_MATCH` gate with deterministic fallback; geofence endpoints unchanged; UI polls and acks; recall debug panel present.

This spec fixes only the findings below.

## Contracts you must not break

- `POST /query` request `{query, session_id?}` and `JeevesResponse` shape (`response_type`, `text`, `image_path` URL-form, `data`).
- `GET /proactive/pending?session_id=` and `POST /proactive/{id}/ack` response shapes; the UI consumes them as-is.
- Geofence and alert endpoint shapes; `/storage` and `/capture` static mounts.
- No deletes on the `events` collection, ever; consolidation stays Chroma-only removal.
- Capture debounces, thresholds, fps, screenshot timing, microphone behavior — intentional, untouched.
- Patient-facing text never contains raw exception strings (this spec extends that rule to persisted fields).
- Both `uvicorn Blue_dream_agents.api:app` and `python Capture/camera_feed.py` keep working.

## Fix designs

Line anchors are from the July 19 audit; treat them as approximate if surrounding code has shifted.

### A1 — Proactive media path stored form (`Blue_dream_agents/proactive_service.py` ~line 123, `api.py` `/proactive/pending`)

`create_message` currently persists `"image_path": to_url_path(image_path)`, putting URL form (`/storage/...`) into Mongo — the only collection violating the storage rule. Change the write to `to_stored_path(image_path)`; convert with `to_url_path(normalize_stored_path(...))` when serializing pending messages in the API response. `normalize_stored_path` already re-roots mount-prefixed input, so legacy documents holding `/storage/...` values normalize correctly at read time — no migration. Update/extend the proactive tests to assert the stored form in Mongo and the URL form in the response, with a legacy-document case.

### A2 — Reminders in the working-memory block (`Blue_dream_agents/jeeves.py`)

Today only profile facts are injected. Add a small renderer (e.g. in `reminder_service` or beside `render_unpinned_profile_block`) that reads active reminders due today — time reminders due today plus event reminders valid today — via the existing indexed reads, and renders at most ~5 lines ("Reminder: take medication at 9:00 AM"). Inject it wherever the profile block is injected: general chat (~459–468), semantic synthesis (~342–353), insufficient-evidence fallback (~398–403). Plain Mongo read on the request path (milliseconds); never embedded; failures degrade to omitting the block, never to an error.

### A3 — Profile facts on object/time routes (`jeeves.py` ~508–553)

The object-search and time-window answers build prompts with no profile facts. Add the same profile block (and the A2 reminder block) to both. Keep the change surgical — prompt assembly only, no routing changes.

### A4 — Alert delivery details (`Blue_dream_agents/alert_service.py` ~361, ~685)

Both spots persist `{"error": str(exc)}` into `delivery_details`, which `serialize_alert` returns verbatim on patient-role endpoints. Replace with a fixed short string (e.g. `"delivery failed"`); `logger.exception` server-side. `delivery_status` semantics unchanged.

### A5 — Safety assessment reason (`Blue_dream_agents/consolidator.py` ~233–235)

`empty_safety_assessment(f"Safety assessment failed: {exc}")` writes raw exception text into the durable event record; the reason later feeds hazard-text selection and the importance-scoring prompt. Use a fixed reason: `"Safety assessment unavailable for this recording."`; `logger.exception` for the traceback.

### A6 — Consolidated re-embed guard (`consolidator.py` ~163–174)

The duplicate-ingest path calls `index_memory_event(existing_event)` unconditionally; a capture retry for a consolidated event would re-enter Chroma (self-heals on the next sync, but is an inconsistency window). Guard: skip indexing when `existing_event.lifecycle_status == "consolidated"`.

### A7 — Daily reminder completion (`Blue_dream_agents/reminder_service.py` ~191–227, `api.py` `/reminders/{id}/done`)

`mark_done` rolls a `daily` reminder's `due_at` forward for every caller, so the API done endpoint can never complete one, and no archive path exists despite `status: archived` in the schema. Split the semantics — e.g. `mark_done(reminder_id, *, source)` or a separate `complete_reminder()`: the proactive-delivery caller keeps roll-forward (spec 0006 design behavior); the API caller sets a terminal status (`archived`). No new endpoint required.

### A8 — Pytest collection

`Blue_dream_agents/test_image_object_pipeline.py` is a CLI utility whose name matches pytest's default pattern; with no `testpaths` config, bare `pytest` from the root imports it (pulling the LLM client stack) during collection. Preferred fix: add `testpaths = tests` (a `pytest.ini` or `[tool.pytest.ini_options]`). If any existing `conftest.py` behavior depends on rootdir resolution, verify `python -m pytest tests/` output is unchanged.

### A9 — Gemini spatial parsing (`Blue_dream_agents/gemini_spatial.py` ~46–80)

`_parse_json_payload` and the local fence stripper duplicate the provider layer's hardening helpers. Import and reuse the shared helpers from `Blue_dream_agents/llm/client.py` (export them if module-private). Keep the best-effort box normalization; output behavior must not change (it is the licensed fallback path).

### A10 — `run_semantic_query` synthesis (`Blue_dream_agents/semantic_search.py` ~398–427)

`_summarize_matches` synthesizes without profile facts; production `/query` doesn't use it (jeeves has its own profile-aware synthesis), only the smoke test does. Minimum fix: docstring marking it smoke-test-only. Better if cheap: pass the profile block through.

### A11 — `presigned_url` TTL (`Blue_dream_agents/oss_media.py` ~60–68)

Add `ttl: int | None = None` defaulting to the settings value, keeping the existing bounds check. Matches the spec 0005 design signature; no caller changes required.

### A12 — `audio_capture.py` `__main__` (`Capture/audio_capture.py` ~164–166)

The standalone debug block passes `device_index=-1` (invalid for PyAudio; the prompt that mapped -1 → None is commented out). Map -1 → `None`. Debug path only; the capture pipeline is unaffected.

### B1–B3 — Documentation

- `TECHNICAL_DESIGN.md` Critical Design Rules: "cloud ingestion is opt-in via `INGEST_URL`" → phrase as delivered by spec 0010 (currently not implemented anywhere).
- `TECHNICAL_DESIGN.md` Intentional Design Decisions: add fall-alert targeting (caretaker-only; patient proactive warnings come from safety-agent hazard alerts).
- `TECHNICAL_DESIGN.md` env surface: enumerate `LLM_SYNTHESIS_MODEL`, `LLM_TRANSCRIBE_MODEL`, `LLM_TTS_MODEL`, `EMBED_BATCH_SIZE`, `GEMINI_SPATIAL_MODEL`, `LLM_DEFAULT_TEMPERATURE`, `LLM_DEFAULT_MAX_TOKENS`, `LLM_REQUEST_TIMEOUT_SECONDS`.

## Risks and mitigations

- **Prompt growth (A2/A3):** cap reminders at ~5 lines; profile block is already capped. No token-budget change to recall packing.
- **`mark_done` split (A7):** the proactive path is covered by existing tests (roll-forward, dated one-shot); add a regression test for each caller's semantics before refactoring.
- **A9 refactor:** spatial grounding has no offline test harness beyond unit tests — keep the refactor mechanical (same inputs → same parsed output) and rely on the existing gemini_spatial unit tests.
- **A1 legacy data:** read-time normalization covers existing documents; do not write a migration.
