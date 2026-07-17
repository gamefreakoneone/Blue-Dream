# 0005 Qwen Provider Tasks

## Prerequisites

- [ ] Spec 0003 completed (provider layer merged with offline tests passing; this spec performs the first live validation).
- [ ] `DASHSCOPE_API_KEY` (or its `QWEN_APIKEY` fallback) present in `.env`.

## Spike (FIRST — timebox ~45 min; record all findings in status.md)

- [ ] `scripts/dashscope_spike.py`: base URL + text completion on qwen-plus.
- [ ] Confirm available model names (text/synthesis/vision/embedding).
- [ ] JSON mode (`response_format json_object`) on the text model.
- [ ] `/embeddings` + `text-embedding-v4`: availability, `dimensions` param, batch limit.
- [ ] `qwen-vl-max` single-image presence check + grounding output format/coordinate convention.
- [ ] Multi-image sequential-frames request: accepted? size limits?
- [ ] ASR endpoint shape (compatible-mode `/audio` vs native SDK) + TTS model identification for spec 0009.

## Implementation Tasks

- [ ] Fill qwen presets in `llm/settings.py` / `model_registry.py` with spike-confirmed values.
- [ ] Set qwen embedding batch size + dimension handling in `embed_texts`.
- [ ] Wire `TRANSCRIBE_PROVIDER=qwen` (compatible-mode or `llm/dashscope_audio.py` native helper; pin `dashscope` if used).
- [ ] Add the Qwen profile block to `.env.example`.
- [ ] STRETCH: `Blue_dream_agents/spatial.py` dispatch + Qwen-VL grounding + shared rendering refactor; switch `object_detector.py`/`alert_service.py` to it.
- [ ] STRETCH: `frame_sampler.py` + `VIDEO_PROVIDER=qwen` branch in `video_agent.py` with Gemini fallback.

## Tests

- [ ] Registry tests extended for qwen.
- [ ] `tests/test_spatial_dispatch.py` (if stretch attempted): dispatch, coordinate math both conventions, fallback trigger.
- [ ] `tests/test_frame_sampler.py` (if stretch attempted).
- [ ] Full suite passes without live keys (providers mocked).

## Manual Checks (first live end-to-end gate for the provider layer — includes the checks deferred from spec 0003)

- [ ] `LLM_PROVIDER=qwen EMBEDDING_PROVIDER=qwen`: object, time, semantic, general queries all answer end-to-end.
- [ ] `memory_events__qwen__*` collection built from Mongo; semantic answers grounded.
- [ ] One ingestion (or re-ingest) with Qwen transcription.
- [ ] STRETCH: Qwen-VL highlight box on a known-object screenshot; frame-sampled description compared against Gemini's.

## Wrap-Up

- [ ] Spike findings + evidence in `status.md`; update `docs/FEATURE_STATUS.md`; commit.
