# 0005 Qwen Provider Requirements

## Goal

Wire Qwen models on Qwen Cloud (DashScope) into the provider layer so `LLM_PROVIDER=qwen` runs the entire reasoning stack — routing, synthesis, evidence judging, vision presence checks, spatial grounding, video understanding (via the OSS video bridge), and semantic embeddings — on Qwen. This is the eligibility core of the Qwen Cloud MemoryAgent submission. A mandatory verification spike runs FIRST and gates every dependent decision.

Model targets reflect the current Qwen Cloud catalog (checked 2026-07-18 against https://www.qwencloud.com/models): `qwen3.7-plus` for all text tasks (routing/judging/synthesis), `qwen3-vl-flash` for vision presence checks and OSS-URL video understanding, `qwen3-vl-plus` for spatial grounding (the documented high-precision 2D/3D localization model), `text-embedding-v4` for embeddings, `qwen3-asr-flash` for ASR. Availability fallback ladder if a model is missing on the account: `qwen3.7-plus` → `qwen3.6-plus` → `qwen-plus`; `qwen3-vl-plus`/`qwen3-vl-flash` → `qwen-vl-max`. The spike confirms what actually lands; record the outcome in `status.md`.

## The Spike (do this before any wiring — timebox ~45 minutes)

Small throwaway script (`scripts/dashscope_spike.py`, committed for the record) that verifies against the live account:

1. Correct base URL for the account region (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1` vs the China endpoint) — one text completion on `qwen3.7-plus`.
2. Current model names actually available to the account (list or trial-call: `qwen3.7-plus`, `qwen3-vl-plus`, `qwen3-vl-flash`; on a miss, walk the fallback ladder from the Goal section and adjust presets to what exists).
3. `response_format={"type":"json_object"}` on `qwen3.7-plus` — does it honor JSON mode?
4. Thinking mode on `qwen3.7-plus` in compatible mode: is thinking on by default? Does `enable_thinking: false` pass through (`extra_body`) and work on non-streaming JSON-mode calls? Note rough routing-call latency with thinking off — all text traffic runs on this plus-tier model.
5. `/embeddings` with `text-embedding-v4`: available? `dimensions` param honored? max batch size per request?
6. `qwen3-vl-flash` with one base64 image: presence check works? Then a grounding prompt on `qwen3-vl-plus`: what bounding-box format and coordinate convention (absolute pixels vs 0–1000 normalized) does it return?
7. Multiple images as sequential frames in one `qwen3-vl-flash` request: accepted? request-size limit encountered?
8. ASR: does compatible mode expose OpenAI-style `/audio/transcriptions`? If not, verify the native `dashscope` SDK call for `qwen3-asr-flash` (check whether the `-filetrans` variant is the right shape for stored audio files). TTS: confirm `qwen3-tts-flash` + call shape (needed by spec 0009).
9. OSS video round-trip: `oss2` upload of one stored recording to the `memoria` bucket + `sign_url` presigned URL; then `qwen3-vl-flash` accepts that URL as a `video_url` content part and answers a question about clip content.
10. Record the effective video size/duration ceilings for URL input against our typical clip sizes (docs state 2 GB / up to 1 h for Qwen3-VL by URL; inline base64 is capped at 10 MB — the reason for the OSS bridge).

Record every answer in this spec's `status.md` before proceeding. If a capability fails, apply the documented fallback rather than fighting it.

## Functional Requirements

- `LLM_PROVIDER=qwen` routes text, structured, and vision-presence calls through DashScope with the models confirmed by the spike.
- `EMBEDDING_PROVIDER=qwen` embeds via DashScope; the Chroma collection `memory_events__qwen__{model}__{dim}` builds from MongoDB and serves semantic recall.
- `TRANSCRIBE_PROVIDER=qwen` transcribes ingestion audio via DashScope (compatible-mode `/audio` or native `dashscope` SDK per the spike); OpenAI remains the fallback config.
- Structured-output hardening applies unchanged; if JSON mode is unsupported for a model, the schema-in-prompt + extraction path carries it.
- `VIDEO_PROVIDER=qwen`: the consolidator uploads the finished video to the private OSS bucket at ingestion (`Blue_dream_agents/oss_media.py`, key mirrors the stored relative path, `video_oss_key` saved on the event) and `video_agent.py` feeds a presigned URL to `qwen3-vl-flash` via `invoke_video_structured(video_url=...)`. Fallback ladder: OSS-URL Qwen video understanding → existing full-video Gemini analysis → partial event. Frame sampling is intentionally not used because recordings can be long and need full temporal context. OSS being unreachable degrades to Gemini; it never blocks event ingestion.
- `SPATIAL_PROVIDER=qwen`: Qwen-VL grounding on `qwen3-vl-plus` replaces Gemini for object-highlight bounding boxes, with the coordinate convention from the spike; Gemini remains the fallback on any Qwen grounding failure. (First cut lever if the schedule slips: drop back to the Gemini fallback.)

## Technical Constraints

- All calls go through `llm/client.py`; no module talks to DashScope directly except a possible thin native-SDK ASR/TTS helper inside the llm package (if compatible mode lacks audio endpoints).
- If the native `dashscope` SDK is needed, pin it in `requirements.txt`. Pin `oss2` in the same change that introduces `oss_media.py`.
- The OSS bucket stays private; videos are reachable only through presigned URLs with a bounded TTL (`OSS_PRESIGN_TTL_SECONDS`). Credentials come from `OSS_ACCESS_KEY_ID`/`OSS_ACCESS_KEY_SECRET` (+ `OSS_BUCKET`, `OSS_ENDPOINT`) in `.env`; a missing OSS config produces a clear log + fallback, never a crash.
- Never delete or overwrite any other provider's Chroma collections.

## Non-Requirements

- No TTS wiring (spec 0009 consumes the spike's TTS findings).
- No GPT-5.6 work (spec 0012).

## Acceptance Criteria

- Spike findings recorded in `status.md` with working example payloads.
- With `LLM_PROVIDER=qwen` + `EMBEDDING_PROVIDER=qwen`: privacy-safe textual routes answer end-to-end. Existing-memory semantic indexing/recall is run only where the execution environment permits the user-authorized export of those records.
- The production `TRANSCRIBE_PROVIDER=qwen` function returns a non-empty transcript for a genuine stored audio file. A new Mongo event is not required solely for validation; unmatched video/audio must never be combined into a false memory.
- With `VIDEO_PROVIDER=qwen`: one genuine stored video is uploaded/deduplicated under its canonical `Storage/...` OSS key and produces a usable structured Qwen description via the presigned-URL path. `video_oss_key` persistence remains covered by mocked consolidator/schema tests when no genuine matched event is ingested.
- With `SPATIAL_PROVIDER=qwen`: one stored screenshot produces a visually correct Qwen-VL highlight box on a known object. Per user direction, no live Gemini media comparison is required; its fallback remains mocked.
- Full pytest suite passes with mocked providers (no live-key dependence in CI-style runs).
