# 0005 Qwen Provider Tasks

## Prerequisites

- [ ] Spec 0003 completed (provider layer merged with offline tests passing; this spec performs the first live validation).
- [ ] `DASHSCOPE_API_KEY` (or its `QWEN_APIKEY` fallback) present in `.env`.
- [ ] OSS credentials present in `.env` as `OSS_ACCESS_KEY_ID`/`OSS_ACCESS_KEY_SECRET` (+ `OSS_BUCKET=memoria`, `OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com`).

## Spike (FIRST — timebox ~45 min; record all findings in status.md)

- [ ] `scripts/dashscope_spike.py`: base URL + text completion on qwen-plus.
- [ ] Confirm available model names (text/synthesis/vision/embedding).
- [ ] JSON mode (`response_format json_object`) on the text model.
- [ ] `/embeddings` + `text-embedding-v4`: availability, `dimensions` param, batch limit.
- [ ] `qwen-vl-max` single-image presence check + grounding output format/coordinate convention.
- [ ] Multi-image sequential-frames request: accepted? size limits?
- [ ] ASR endpoint shape (compatible-mode `/audio` vs native SDK) + TTS model identification for spec 0009.
- [ ] OSS round-trip: `oss2` upload of one stored recording + `sign_url`; `qwen-vl-max` answers about clip content from the presigned `video_url`.
- [ ] Record effective URL-video size/duration ceilings vs our typical clips.

## Implementation Tasks

- [ ] Fill qwen presets in `llm/settings.py` / `model_registry.py` with spike-confirmed values.
- [ ] Set qwen embedding batch size + dimension handling in `embed_texts`.
- [ ] Wire `TRANSCRIBE_PROVIDER=qwen` (compatible-mode or `llm/dashscope_audio.py` native helper; pin `dashscope` if used).
- [ ] Add the Qwen profile block (incl. `OSS_*` vars) to `.env.example`.
- [ ] `Blue_dream_agents/oss_media.py` (`upload_video`, `presigned_url`); pin `oss2` in `requirements.txt`.
- [ ] Consolidator: upload video to OSS before the understanding call; store `video_oss_key` on the event.
- [ ] `VIDEO_PROVIDER=qwen` branch in `video_agent.py`: presigned `video_url` primary → `frame_sampler.py` fallback → Gemini fallback.
- [ ] STRETCH: `Blue_dream_agents/spatial.py` dispatch + Qwen-VL grounding + shared rendering refactor; switch `object_detector.py`/`alert_service.py` to it.

## Tests

- [ ] Registry tests extended for qwen.
- [ ] `tests/test_oss_media.py`: key derivation, missing-config error, presign shape, fallback trigger (mocked, no network).
- [ ] `tests/test_frame_sampler.py`.
- [ ] `tests/test_spatial_dispatch.py` (if stretch attempted): dispatch, coordinate math both conventions, fallback trigger.
- [ ] Full suite passes without live keys (providers mocked).

## Manual Checks (first live end-to-end gate for the provider layer — includes the checks deferred from spec 0003)

- [ ] `LLM_PROVIDER=qwen EMBEDDING_PROVIDER=qwen`: object, time, semantic, general queries all answer end-to-end.
- [ ] `memory_events__qwen__*` collection built from Mongo; semantic answers grounded.
- [ ] One ingestion (or re-ingest) with Qwen transcription.
- [ ] One stored video through the OSS-URL path: uploaded, `video_oss_key` on the event, Qwen description compared against the stored Gemini description.
- [ ] STRETCH: Qwen-VL highlight box on a known-object screenshot.

## Wrap-Up

- [ ] Spike findings + evidence in `status.md`; update `docs/FEATURE_STATUS.md`; commit.
