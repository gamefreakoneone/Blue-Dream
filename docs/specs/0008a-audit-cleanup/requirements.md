# 0008a Audit Cleanup Requirements

## Goal

A full audit of specs 0001–0008 against `AGENTS.md`, `requirements.md`, and `TECHNICAL_DESIGN.md` (run July 19, 2026) found the implementation strongly aligned with the design: no broken stable contracts, no data-loss paths, all proactive triggers and the recall pipeline match the documented behavior. It also found a short list of small, targeted gaps. This spec closes all of them in one change-set **before** spec 0009, so the voice work and both submissions build on a clean base.

## Functional Requirements

### Storage contract

- **A1 — Proactive message media paths.** `proactive_messages` documents must store media paths in the relative-POSIX stored form (like every other collection), converting to URL form only at the API boundary in the `/proactive/pending` response. Legacy documents already written with `/storage/...` URL values must keep working via read-time normalization (`normalize_stored_path` already handles mount-prefixed input).

### Working memory injection

- **A2 — Reminders in chat prompts.** The working-memory block injected into answer prompts must include today's active reminders alongside profile facts (plain indexed MongoDB read via `reminder_service`; no embedding). Inject into the general-chat prompt, the semantic synthesis prompt, and the insufficient-evidence fallback. Keep the block small: cap the count, one line per reminder. A patient asking "what do I need to do today?" must get an answer that reflects their due reminders.
- **A3 — Profile facts on all answer routes.** The object-search and time-window answer prompts must receive the same profile-fact block as the semantic and general routes, making "profile facts are always injected into answer prompts" literally true.

### Exception hygiene

- **A4 — Alert delivery details.** Alert delivery failures must not persist or return raw exception strings in `delivery_details`. Log the exception server-side; store a fixed short status string.
- **A5 — Safety assessment reason.** A failed safety assessment must not persist the raw exception message into `safety_assessment.reason` on the event. Use a fixed reason string; keep the full traceback in server logs.

### Lifecycle edges

- **A6 — Consolidated re-embed guard.** The consolidator's duplicate-ingest path must not re-index an event whose `lifecycle_status` is `consolidated` into ChromaDB.
- **A7 — Daily reminders completable.** `POST /reminders/{reminder_id}/done` must actually complete a daily reminder (status flip, e.g. `archived`), while proactive delivery keeps the existing roll-forward behavior. The two callers of `mark_done` get distinct semantics.

### Tooling and latent items

- **A8 — Pytest collection.** Bare `pytest` from the repository root must collect only `tests/` (add `testpaths` config, or rename `Blue_dream_agents/test_image_object_pipeline.py`, which is a CLI utility, not a test).
- **A9 — Gemini spatial JSON parsing.** The Gemini spatial fallback must reuse the shared JSON-hardening helpers (fence stripping / embedded-JSON extraction) from the provider layer instead of its local duplicates. Behavior-preserving refactor.
- **A10 — `run_semantic_query` synthesis.** Its internal synthesis path omits profile facts; either add the profile block or mark the function smoke-test-only in its docstring so no future caller mistakes it for the production path.
- **A11 — `presigned_url` TTL parameter.** `oss_media.presigned_url` accepts an optional `ttl` argument defaulting to the settings value, matching the spec 0005 design signature.
- **A12 — `audio_capture.py` standalone block.** The `__main__` debug block maps `device_index=-1` to `None` before constructing `AudioRecorder`.

### Documentation corrections

- **B1 —** `TECHNICAL_DESIGN.md` Critical Design Rules: rephrase `INGEST_URL` as planned capability delivered by spec 0010, not present-tense.
- **B2 —** `TECHNICAL_DESIGN.md` Intentional Design Decisions: record that YOLO fall alerts target caretakers only; the patient-facing proactive warning path is for hazard alerts from the safety agent. This is intentional — do not "fix" it.
- **B3 —** `TECHNICAL_DESIGN.md` env surface: add the override vars that exist in code but are not enumerated (`LLM_SYNTHESIS_MODEL`, `LLM_TRANSCRIBE_MODEL`, `LLM_TTS_MODEL`, `EMBED_BATCH_SIZE`, `GEMINI_SPATIAL_MODEL`, `LLM_DEFAULT_TEMPERATURE`, `LLM_DEFAULT_MAX_TOKENS`, `LLM_REQUEST_TIMEOUT_SECONDS`).

## Non-Requirements (deferred by design — do NOT fix)

- OpenAI strict `json_schema` structured output (`llm/client.py` `NotImplementedError`) — lands with spec 0012's provider flip.
- TTS `synthesize_speech` (`NotImplementedError`) — lands with spec 0009.
- The `frame_paths` branch of `invoke_video_structured` — sanctioned evidence-only capability, not a production fallback.
- The unused compound lifecycle index and pinned recall-budget overflow — documented deferrals in `docs/specs/0007-memory-lifecycle/course-correction.md`.
- Fall alerts targeting caretakers only — intentional (B2 documents it).
- No changes to capture debounce values, screenshot timing, fps, or microphone behavior (intentional, see `TECHNICAL_DESIGN.md`).

## Acceptance Criteria

- Full suite green: `python -m pytest tests/` in the `Project-Memoria` conda environment, zero failures/errors, including the new tests listed in `tasks.md`.
- A new proactive message with an image stores a relative POSIX path in Mongo and returns a `/storage/...` URL from `/proactive/pending`; legacy URL-form documents still render.
- With a due-today reminder present, a chat question like "what do I need to do today?" produces an answer referencing it.
- `POST /reminders/{id}/done` on a daily reminder completes it; proactive delivery of a daily reminder still rolls `due_at` forward.
- No `str(exc)` reaches `delivery_details` or `safety_assessment.reason`; grep confirms.
- Bare `pytest` from the repo root collects only `tests/`.
- `docs/FEATURE_STATUS.md` and this spec's `status.md`/`tasks.md` updated with evidence in the same change; one descriptive commit.
