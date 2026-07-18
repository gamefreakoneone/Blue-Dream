# 0003 LLM Provider Layer Tasks

## Prerequisites

- [x] Specs 0001–0002 implementation prerequisites satisfied (tests and `media_paths` exist). Spec 0002 remains In progress only on deferred live checks.
- [x] `DASHSCOPE_API_KEY` (or its `QWEN_APIKEY` fallback) present in `.env` for the follow-on 0005 live validation. No local Ollama required.

## Implementation Tasks

- [x] Rewrite `llm/settings.py`: drop Nova/Bedrock fields; add provider selection, endpoints, models, and key fallback while preserving shared configuration.
- [x] Rewrite `llm/model_registry.py` as `resolve(task) -> TaskTarget` with provider presets and override precedence.
- [x] Create `llm/client.py`: cached AsyncOpenAI clients; text and structured calls; image/video calls; chunked validated embeddings; OpenAI transcription fallback; pending Qwen ASR/TTS stubs.
- [x] Migrate all application and benchmark consumers directly to `llm.client`; delete `llm/strands_runtime.py` instead of retaining a zero-consumer shim.
- [x] Delete `llm/bedrock_client.py`, `llm/ollama_runtime.py`, and `llm/embedding_client.py`; make `audio_transcribe.py` an async shim over `client.transcribe_audio`.
- [x] Update FastAPI lifespan to await `client.close_llm_clients` before Mongo cleanup, including index-failure coverage.
- [x] Update consolidator concurrency for async transcription and migrate its mocks.
- [x] Merge semantic retrieval/query behind `_run_semantic`; await embeddings directly and keep blocking Chroma calls off the event loop.
- [x] Use provider-specific Chroma collections and active-only rebuilds that preserve siblings.
- [x] Remove `strands-agents` and `boto3`; keep the pinned OpenAI SDK.
- [x] Update environment, setup, architecture, benchmark, and spec documentation.

## Tests

- [x] Registry tests cover presets, overrides, key fallback/errors, endpoint normalization, and dimensions.
- [x] Client tests cover JSON hardening/retry, native JSON mode, image/video construction, embedding behavior, OpenAI transcription shape, and pending Qwen ASR.
- [x] Temporary Chroma tests prove provider switches create siblings and active rebuilds preserve them.
- [x] API lifespan, consolidator, semantic-error, benchmark, and test-environment coverage updated.
- [x] Full offline suite passes.

## Manual Checks (offline gate — live checks run in spec 0005 on Qwen)

- [x] Source grep for `bedrock|strands|boto3|nova` has zero Python-source hits under `Blue_dream_agents/`; this means no live Strands/Bedrock SDK usage.
- [x] Backend imports and resolves the Qwen profile with `LLM_PROVIDER=qwen` without a live model call.
- [x] OpenAI `Recording.m4a` smoke **skipped/non-gating, superseded by the spec 0005 Qwen ASR live check**. No OpenAI key is configured; mocked fallback coverage remains here.

## Wrap-Up

- [x] Update `docs/FEATURE_STATUS.md`, spec 0002 deferred-live-check notes, and `status.md` with evidence; commit.
