# 0003 LLM Provider Layer Requirements

## Goal

Replace the three coexisting LLM paths (Ollama HTTP runtime, Strands/Bedrock/Nova, per-module Gemini env reads for text tasks) with one async client speaking the OpenAI chat-completions protocol. `LLM_PROVIDER=qwen|openai|ollama` switches every reasoning, vision, and embedding call.

This spec lands with **offline validation only** (mocked-SDK pytest for JSON hardening, registry resolution, and contract shapes); the **first live end-to-end validation happens in spec 0005 on `LLM_PROVIDER=qwen`**, immediately after the DashScope spike. Rationale: Ollama is not installed on the dev machine, and the pre-change live baseline (Bedrock/Nova per the current `.env`) is deleted by this spec, so provider-identical "behavior-neutral" checks are unverifiable here. The Ollama profile stays in the client as an optional preset (it is just another OpenAI-compatible endpoint) but is never a prerequisite and is not validated in this rebuild.

## Functional Requirements

- New `Blue_dream_agents/llm/client.py` exposing: `invoke_text`, `invoke_structured`, `invoke_multimodal_structured`, `invoke_video_structured` (new), `embed_texts`, `transcribe_audio`, `synthesize_speech` (stubs may raise `NotImplementedError` for providers wired in later specs).
- The JSON hardening from `ollama_runtime.py` (fence stripping, embedded-JSON extraction, Pydantic validation, one strict retry) is preserved verbatim and applied to every structured call on every provider.
- Native structured modes layered on top where supported: `response_format={"type":"json_object"}` (DashScope, Ollama), `json_schema` strict structured outputs (GPT-5.6; the schema branch itself is completed in spec 0012).
- `llm/settings.py` rewritten: all Nova/Bedrock fields removed; new provider env surface added; the custom `.env` parser retained. The DashScope key is read from `DASHSCOPE_API_KEY` with a **`QWEN_APIKEY` fallback** (the name already used in the local `.env`); both documented in `.env.example`.
- `llm/model_registry.py` rewritten to resolve `(provider, model, base_url, api_key, supports_json_mode)` per task: `router | synthesis | judge | vision | spatial | video | embedding | transcribe | tts`.
- `llm/strands_runtime.py` becomes a thin shim re-exporting `client.py` functions so `jeeves.py`, `time_agent.py`, `object_detector.py`, `safety_agent.py` need no import changes.
- Dead provider code deleted: `llm/bedrock_client.py`, all Bedrock/Strands branches, `llm/ollama_runtime.py` (after porting), the Bedrock path in `llm/embedding_client.py` (embeddings move into `client.py`), `strands-agents` and `boto3` removed from `requirements.txt`; `openai` SDK pinned.
- Per-provider Chroma collections: `memory_events__{provider}__{model_slug}__{dim}`; switching providers rebuilds from MongoDB and never destroys another provider's collection. The Chroma internal-SQLite inspection and the rmtree reset path are deleted.
- `semantic_search.py`: the ~80 duplicated lines between `run_semantic_retrieval` and `run_semantic_query` are merged into one function with a synthesis flag.

## Technical Constraints

- Use `openai.AsyncOpenAI` with per-task `base_url`/`api_key`; chat.completions API (not the responses API) as the cross-provider common denominator.
- Embedding calls must be async (httpx/OpenAI SDK), removing the event-loop-blocking synchronous urllib path.
- Ollama is reached through its OpenAI-compatible `/v1` endpoint (`OLLAMA_BASE_URL` + `/v1`, api_key `"ollama"`).
- Gemini stays untouched for video/spatial in this spec (`video_agent.py`, `gemini_spatial.py` unchanged).

## Non-Requirements

- No Qwen/DashScope wiring beyond config plumbing (spec 0005).
- No GPT-5.6-specific branches beyond leaving the hook (spec 0012).
- No change to prompts or routing logic.

## Acceptance Criteria

- `pytest` passes, including new `tests/test_llm_client_json.py` (hardening behaviors) and existing contract tests — this offline suite is the gate for this spec; the four live `/query` route checks and the qwen Chroma collection rebuild run in spec 0005.
- `grep -r "strands\|bedrock\|boto3\|nova" Blue_dream_agents/` returns no live code references.
- Switching `EMBEDDING_PROVIDER` values creates sibling Chroma collections without touching existing ones.
