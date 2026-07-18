# 0003 LLM Provider Layer Status

## Status

Completed on 2026-07-17 with the offline gate. Live Qwen model, ASR, video, and end-to-end query validation remain explicitly assigned to spec 0005; spec 0004 and 0005 were not started by this change.

## Delivered

- Added provider settings, `TaskTarget` resolution, and one cached async OpenAI-protocol client for text, structured JSON, image/video message construction, embeddings, and transcription capability boundaries.
- Migrated all internal and benchmark consumers directly to `llm.client`; deleted the zero-consumer shim and all legacy Strands/Bedrock/Ollama/embedding runtime modules.
- Changed the FastAPI lifespan to await `close_llm_clients()` before Mongo cleanup, including index-initialization failure coverage.
- Made transcription async through the consolidator and retained mocked OpenAI fallback plumbing; Qwen ASR/TTS remain explicit pending stubs for their later specs.
- Consolidated semantic query logic and introduced provider/model/dimension Chroma collections with active-only repair/rebuild behavior that preserves sibling collections.
- Updated requirements, environment/setup documentation, benchmark support, spec 0002 deferred validation notes, and the feature ledger.

## Verification Evidence

- `conda run -n Project-Memoria python -m pytest tests/ -q` — **49 passed**, one pre-existing `StarletteDeprecationWarning`, in 5.36 seconds.
- `conda run -n Project-Memoria python -m compileall -q Blue_dream_agents` — passed with no compile errors.
- Python-source grep for `bedrock|strands|boto3|nova` under `Blue_dream_agents/` — **zero hits**, interpreted as no live Strands/Bedrock SDK usage.
- Qwen-profile backend smoke with `LLM_PROVIDER=qwen` imported `Blue_dream_agents.api:app` and resolved `router` to `qwen/qwen-plus` without a network/model call: `backend=Jeeves API; provider=qwen; model=qwen-plus`.
- Provider/vector tests use temporary Chroma state and prove sibling collections survive provider switches and active collection rebuilds.
- The conda wrapper printed its known non-fatal missing OpenCL `temp.txt` cleanup message after successful Python commands.
- The `Recording.m4a` OpenAI live smoke was skipped/non-gating because no OpenAI key is configured; it is superseded by the spec 0005 Qwen ASR live check. Mocked OpenAI file-shape coverage passes here.

## Commit Evidence

- Planning-document precursor: `20a40db` (`docs: refine Qwen provider and submission plans`).
- Implementation: the dated `feat: implement spec 0003 llm provider layer` commit containing this status file; its SHA is reported in the implementation handoff.
