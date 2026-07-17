# 0003 LLM Provider Layer Tasks

## Prerequisites

- [ ] Specs 0001–0002 completed (tests exist; media_paths available for image loading).
- [ ] `DASHSCOPE_API_KEY` (or its `QWEN_APIKEY` fallback) present in `.env` — used by the follow-on 0005 live validation. No local Ollama required.

## Implementation Tasks

- [ ] Rewrite `llm/settings.py`: drop Nova/Bedrock fields; add `LLM_PROVIDER` + per-capability provider vars + DashScope/OpenAI/Ollama endpoints + per-task model overrides; keep the custom `.env` parser; read `DASHSCOPE_API_KEY` with `QWEN_APIKEY` fallback.
- [ ] Rewrite `llm/model_registry.py` as `resolve(task) -> TaskTarget` with provider presets and override precedence.
- [ ] Create `llm/client.py`: cached AsyncOpenAI clients; `invoke_text`, `invoke_structured` (ported hardening + retry), `invoke_multimodal_structured` (base64 image parts), `invoke_video_structured` (frames variant), `embed_texts` (chunked, dim-validated), `transcribe_audio` (openai branch), `synthesize_speech` stub.
- [ ] Reduce `llm/strands_runtime.py` to a re-export shim; delete Strands/Bedrock machinery.
- [ ] Delete `llm/bedrock_client.py`, `llm/ollama_runtime.py`, `llm/embedding_client.py`; update `audio_transcribe.py` to a shim over `client.transcribe_audio`.
- [ ] `semantic_search.py`: call `client.embed_texts` directly (async); merge the duplicated retrieval/query functions.
- [ ] `vector_store.py`: per-provider collection naming + metadata; delete SQLite inspection and rmtree reset; simplify mismatch handling to rebuild-from-Mongo.
- [ ] `requirements.txt`: remove `strands-agents`, `boto3`; pin `openai`.
- [ ] Purge Nova/Bedrock/Gemma-runtime references from `.env.example` (and confirm `AGENTS.md`/`TECHNICAL_DESIGN.md` stay accurate).

## Tests

- [ ] `tests/test_llm_client_json.py`: fence stripping, embedded-JSON extraction, strict retry, embed dimension mismatch, batch chunking (mocked SDK).
- [ ] `tests/test_registry.py`: presets, overrides, missing-key errors.
- [ ] Full suite passes.

## Manual Checks (offline gate — live checks run in spec 0005 on Qwen)

- [ ] `grep -ri "bedrock\|strands\|nova" Blue_dream_agents/` → no live code references.
- [ ] Backend starts cleanly with `LLM_PROVIDER=qwen` configured (no import/config errors; live queries deferred to 0005).
- [ ] Ingestion transcription still works (OpenAI path) on one test audio file (`Blue_dream_agents/test_data/Recording.m4a`).

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
