# 0003 LLM Provider Layer Design

## Contracts You Must Not Break

- The call surface used by `jeeves.py`, `time_agent.py`, `object_detector.py`, and `safety_agent.py` after their direct migration to `llm.client`: `invoke_text(...)`, `invoke_structured(...)`, and `invoke_multimodal_structured(...)` keyword signatures stay compatible.
- `JeevesResponse` shapes and all endpoint contracts.
- MongoDB is never touched by this spec; Chroma collections for other providers are never deleted.
- `semantic_search` degradation rule: if embeddings are unavailable, semantic queries return the insufficient-evidence response, never a crash.

## Configuration (`llm/settings.py` rewrite)

Keep the custom `.env` parser (Windows `SET` prefix support, no overwrite of existing env). Remove every Nova/Bedrock field. New surface:

```
LLM_PROVIDER=qwen              # qwen | openai | ollama (dev + Qwen submission run qwen; openai only in spec 0012; ollama optional, requires local install)
EMBEDDING_PROVIDER=            # defaults to LLM_PROVIDER
VIDEO_PROVIDER=gemini          # qwen | gemini (qwen wired in 0005)
SPATIAL_PROVIDER=gemini        # qwen | gemini
TRANSCRIBE_PROVIDER=openai     # qwen | openai
TTS_PROVIDER=none              # qwen | openai | none (wired in 0009/0012)

DASHSCOPE_API_KEY=             # settings fall back to QWEN_APIKEY (the name in the local .env) when unset
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OLLAMA_BASE_URL=http://localhost:11434     # client appends /v1

LLM_TEXT_MODEL=  LLM_SYNTHESIS_MODEL=  LLM_VISION_MODEL=
LLM_EMBEDDING_MODEL=  LLM_EMBEDDING_DIM=
LLM_TRANSCRIBE_MODEL=  LLM_TTS_MODEL=  LLM_VIDEO_MODEL=

# OSS video bridge — used by the 0005 video path (documented here, wired in 0005)
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_BUCKET=memoria
OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
OSS_PRESIGN_TTL_SECONDS=3600
```

Provider presets (used when the per-task override is empty):

| task | qwen | openai | ollama (optional) |
|---|---|---|---|
| text/router/judge | qwen-plus | gpt-5.6 | gemma4:e2b |
| synthesis | qwen-max | gpt-5.6 | gemma4:e2b |
| vision | qwen-vl-max | gpt-5.6 | gemma4:e2b |
| embedding (dim) | text-embedding-v4 (1024) | text-embedding-3-small (1536) | nomic-embed-text (768) |
| transcribe | qwen3-asr-flash | gpt-4o-transcribe | — |
| tts | (0005 spike decides) | gpt-4o-mini-tts | — |

Gemini vars (`GEMINI_API_KEY`, `GEMINI_VIDEO_MODEL`, `GEMINI_SPATIAL_MODEL`, fallbacks, retries) stay as-is.

## `llm/model_registry.py` rewrite

`resolve(task: str) -> TaskTarget` where `TaskTarget = {provider, model, base_url, api_key, supports_json_object: bool, supports_json_schema: bool, embedding_dim: int | None}`. Per-task provider override envs (`EMBEDDING_PROVIDER` etc.) take precedence over `LLM_PROVIDER`. Raise a clear config error naming the missing env var when a key is absent for the resolved provider.

## `llm/client.py`

- One `AsyncOpenAI` instance per `(base_url, api_key)` pair, cached (mirror the existing httpx-client caching pattern in `ollama_runtime.py`).
- `invoke_text(*, prompt, system_prompt=None, model_id=None, temperature=None, max_tokens=None, task="text") -> str` — plain chat.completions call.
- `invoke_structured(*, prompt, output_model, system_prompt=None, task="text", ...) -> BaseModel`:
  1. Build messages; if target `supports_json_object`, pass `response_format={"type": "json_object"}` and include the schema description in the prompt (keep the existing schema-in-prompt text from `ollama_runtime.py`).
  2. **Port verbatim** from `ollama_runtime.py`: `_strip_json_fences`, `_extract_json_payload` (raw_decode scan), Pydantic `model_validate`, and the retry loop that re-issues once with the stricter JSON-only instruction on parse/validation failure. Note: `_structured_messages(retry=...)` in the old file contains an unused retry branch — port the *live* retry mechanism from `_invoke_structured_chat`, not the dead one.
  3. Leave a `supports_json_schema` branch stub (raise `NotImplementedError` if selected) — completed in spec 0012.
- `invoke_multimodal_structured(*, text_prompt, image_path, output_model, ...)` — content parts with base64 data URL (`{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}`), then the same hardening. Load images via `media_paths.to_fs_path`.
- `invoke_video_structured(*, video_url | frame_paths, output_model, ...)` — `video_url` sends a `{"type": "video_url", "video_url": {"url": ...}}` content part (the presigned-OSS-URL path used by spec 0005 as the primary qwen video route); `frame_paths` sends pre-sampled frames as multiple image parts with a sequential-frames instruction (the fallback). Both variants are offline-testable message construction here; live validation of the URL path happens in the 0005 spike.
- `embed_texts(texts: list[str], task="embedding") -> list[list[float]]` — `client.embeddings.create`; chunk requests (`EMBED_BATCH_SIZE` env, default 10) and concatenate; validate returned dimension against `embedding_dim`, raising a descriptive error on mismatch.
- `transcribe_audio(audio_path) -> str` — routes to OpenAI `audio.transcriptions` when `TRANSCRIBE_PROVIDER=openai` (move the logic from `audio_transcribe.py` here; keep that module as a shim calling this). Qwen branch raises `NotImplementedError` until 0005.
- `synthesize_speech(text) -> bytes` — `NotImplementedError` until 0009.

## Direct consumer migration

Migrate application and benchmark imports directly to `llm.client`, preserving public keyword signatures. Delete `llm/strands_runtime.py` together with its Strands imports, Bedrock agent construction, model-ID candidate fallbacks, and unused tool wrapper. No compatibility shim remains because there are no internal consumers that need it.

## Deletions

- `llm/bedrock_client.py`; `llm/ollama_runtime.py` (after porting the hardening + image encoding); the Bedrock branch and the synchronous urllib code in `llm/embedding_client.py` (module deleted; `semantic_search.py` calls `client.embed_texts` directly — it is already async, so remove the `run_in_executor` wrapper).
- `requirements.txt`: remove `strands-agents`, `boto3`; pin `openai`.
- `AGENTS.md`/`.env.example`: remove Nova/Bedrock references in the same change.

## Chroma per-provider collections (`vector_store.py` + `semantic_search.py`)

- `get_event_collection()` computes `name = f"memory_events__{provider}__{slug(model)}__{dim}"` from the resolved embedding target; collection metadata records `{provider, model, dim}`.
- Delete `inspect_production_index` (raw SQLite reads) and `reset_production_index` (rmtree). Mismatch handling reduces to: collection missing or metadata disagrees → treat as empty and rebuild from Mongo via the existing `ensure_semantic_index_synced` full-index path.
- Merge `run_semantic_retrieval` / `run_semantic_query` into `_run_semantic(query, *, synthesize: bool)`; keep both public names as one-line wrappers.

## Tests

- `tests/test_llm_client_json.py` — fence-stripped JSON, embedded JSON in prose, invalid-then-valid retry (mock the AsyncOpenAI client), dimension-mismatch error from `embed_texts`, batch chunking.
- `tests/test_registry.py` — provider preset resolution, per-task override precedence, missing-key error message.
- Existing contract tests still pass unchanged.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
conda run -n Project-Memoria python -m compileall -q Blue_dream_agents
```

This spec's gate is the offline suite plus a source grep for `bedrock|strands|boto3|nova`, interpreted as **no live Strands/Bedrock SDK usage**. Python source under `Blue_dream_agents/` must have zero hits. **Live validation is deferred to spec 0005 (Qwen)**: one `/query` each for object / time / semantic / general and the `memory_events__qwen__text-embedding-v4__1024` rebuild run there, right after the DashScope spike.
