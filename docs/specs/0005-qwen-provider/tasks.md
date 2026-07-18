# 0005 Qwen Provider Tasks

## Prerequisites

- [x] Spec 0003 completed (provider layer merged with offline tests passing; this spec performs the first live validation).
- [x] `DASHSCOPE_API_KEY` (or its `QWEN_APIKEY` fallback) present in `.env`.
- [x] OSS credentials present in `.env` as `OSS_ACCESS_KEY_ID`/`OSS_ACCESS_KEY_SECRET` (+ `OSS_BUCKET=memoria`, `OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com`).

## Spike (FIRST — timebox ~45 min; record all findings in status.md)

- [x] `scripts/dashscope_spike.py`: base URL + text completion on `qwen3.7-plus`.
- [x] Confirm available model names (`qwen3.7-plus`, `qwen3-vl-plus`, `qwen3-vl-flash`; walk the availability fallback ladder on a miss).
- [x] JSON mode (`response_format json_object`) on `qwen3.7-plus`.
- [x] Thinking mode on `qwen3.7-plus`: default state; `enable_thinking: false` pass-through on non-streaming JSON-mode calls; rough routing-call latency with thinking off.
- [x] `/embeddings` + `text-embedding-v4`: availability, `dimensions` param, batch limit.
- [x] `qwen3-vl-flash` single-image presence check; grounding output format/coordinate convention on `qwen3-vl-plus`.
- [x] Multi-image sequential-frames request on `qwen3-vl-flash`: accepted? size limits?
- [x] ASR endpoint shape (compatible-mode `/audio` vs native SDK, incl. the `qwen3-asr-flash-filetrans` variant for stored files) + `qwen3-tts-flash` confirmation for spec 0009.
- [x] OSS round-trip: `oss2` upload of one stored recording + `sign_url`; `qwen3-vl-flash` answers about clip content from the presigned `video_url`.
- [x] Record effective URL-video size/duration ceilings vs our typical clips (docs claim 2 GB / 1 h for Qwen3-VL by URL).

## Implementation Tasks

- [x] Fill qwen presets in `llm/settings.py` / `model_registry.py` with spike-confirmed values (targets: `qwen3.7-plus` text/synthesis, `qwen3-vl-flash` vision/video, `qwen3-vl-plus` spatial; update `tests/test_registry.py` assertions to match).
- [x] Set qwen embedding batch size + dimension handling in `embed_texts`.
- [x] Wire `TRANSCRIBE_PROVIDER=qwen` (compatible-mode or `llm/dashscope_audio.py` native helper; pin `dashscope` if used).
- [x] Add the Qwen profile block (incl. `OSS_*` vars) to `.env.example`.
- [x] `Blue_dream_agents/oss_media.py` (`upload_video`, `presigned_url`); pin `oss2` in `requirements.txt`.
- [x] Consolidator: upload video to OSS before the understanding call; store `video_oss_key` on the event.
- [x] `VIDEO_PROVIDER=qwen` branch in `video_agent.py`: presigned `video_url` primary → existing full-video Gemini fallback → partial event; no frame sampling.
- [x] `Blue_dream_agents/spatial.py` dispatch + Qwen-VL grounding on `qwen3-vl-plus` + shared rendering refactor; switch `object_detector.py`/`alert_service.py` to it. (First cut lever if the schedule slips: stay on the Gemini fallback.)

## Tests

- [x] Registry tests extended for qwen.
- [x] `tests/test_oss_media.py`: key derivation, missing-config error, presign shape, fallback trigger (mocked, no network).
- [x] `tests/test_spatial_dispatch.py`: dispatch, coordinate math both conventions, fallback trigger.
- [x] Full suite passes without live keys (providers mocked).

## Manual Checks (first live end-to-end gate for the provider layer — includes the checks deferred from spec 0003)

- [x] `LLM_PROVIDER=qwen EMBEDDING_PROVIDER=qwen`: privacy-safe general and no-evidence time `/query` routes answer end-to-end. Object media export was excluded by user direction.
- [x] Grounded semantic `/query` gate evaluated: live existing-memory export is prohibited by the execution environment; mocked route coverage plus live Qwen text/embedding checks are recorded instead.
- [x] `memory_events__qwen__*` build gate evaluated: the existing 41 Mongo records were not exported under the same privacy restriction; sibling-collection behavior is covered by tests and the legacy 40-record collection was inspected read-only.
- [x] Production Qwen transcription on a genuine stored audio recording (event insertion waived by user to avoid combining unmatched media).
- [x] One stored video through the OSS-URL production path: canonical key, private presign, and structured Qwen description validated (event insertion and Gemini comparison waived by user).
- [x] Qwen-VL highlight box on a known-object screenshot (`qwen3-vl-plus`), visually inspected; Gemini comparison waived by user.

## Wrap-Up

- [x] Spike findings + evidence in `status.md`; update `docs/FEATURE_STATUS.md`; commit.
