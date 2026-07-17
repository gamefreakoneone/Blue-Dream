# 0005 Qwen Provider Requirements

## Goal

Wire Qwen models on Qwen Cloud (DashScope) into the provider layer so `LLM_PROVIDER=qwen` runs the entire reasoning stack — routing, synthesis, evidence judging, vision presence checks, and semantic embeddings — on Qwen. This is the eligibility core of the Qwen Cloud MemoryAgent submission. A mandatory verification spike runs FIRST and gates every dependent decision.

## The Spike (do this before any wiring — timebox ~45 minutes)

Small throwaway script (`scripts/dashscope_spike.py`, committed for the record) that verifies against the live account:

1. Correct base URL for the account region (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1` vs the China endpoint) — one text completion on `qwen-plus`.
2. Current model names actually available to the account (list or trial-call: `qwen-plus`, `qwen-max`, `qwen-vl-max`; adjust presets to what exists).
3. `response_format={"type":"json_object"}` on the text model — does it honor JSON mode?
4. `/embeddings` with `text-embedding-v4`: available? `dimensions` param honored? max batch size per request?
5. `qwen-vl-max` with one base64 image: presence check works? Then a grounding prompt: what bounding-box format and coordinate convention (absolute pixels vs 0–1000 normalized) does it return?
6. Multiple images as sequential frames in one request: accepted? request-size limit encountered?
7. ASR: does compatible mode expose OpenAI-style `/audio/transcriptions`? If not, verify the native `dashscope` SDK call for `qwen3-asr-flash` (or the current ASR model). TTS: identify the working TTS model + call shape (needed by spec 0009).

Record every answer in this spec's `status.md` before proceeding. If a capability fails, apply the documented fallback rather than fighting it.

## Functional Requirements

- `LLM_PROVIDER=qwen` routes text, structured, and vision-presence calls through DashScope with the models confirmed by the spike.
- `EMBEDDING_PROVIDER=qwen` embeds via DashScope; the Chroma collection `memory_events__qwen__{model}__{dim}` builds from MongoDB and serves semantic recall.
- `TRANSCRIBE_PROVIDER=qwen` transcribes ingestion audio via DashScope (compatible-mode `/audio` or native `dashscope` SDK per the spike); OpenAI remains the fallback config.
- Structured-output hardening applies unchanged; if JSON mode is unsupported for a model, the schema-in-prompt + extraction path carries it.
- Stretch (explicit cut line — skip without guilt if the schedule slips):
  - `SPATIAL_PROVIDER=qwen`: Qwen-VL grounding replaces Gemini for object-highlight bounding boxes, with the coordinate convention from the spike; Gemini remains the fallback.
  - `VIDEO_PROVIDER=qwen`: OpenCV frame sampling (8–16 frames) + `invoke_video_structured` replaces Gemini full-video analysis; Gemini remains the default until this validates.

## Technical Constraints

- All calls go through `llm/client.py`; no module talks to DashScope directly except a possible thin native-SDK ASR/TTS helper inside the llm package (if compatible mode lacks audio endpoints).
- If the native `dashscope` SDK is needed, pin it in `requirements.txt`.
- Never delete or overwrite any other provider's Chroma collections.

## Non-Requirements

- No TTS wiring (spec 0009 consumes the spike's TTS findings).
- No GPT-5.6 work (spec 0012).

## Acceptance Criteria

- Spike findings recorded in `status.md` with working example payloads.
- With `LLM_PROVIDER=qwen` + `EMBEDDING_PROVIDER=qwen`: all four `/query` route types answer correctly end-to-end; semantic recall returns grounded answers from the Qwen collection.
- One ingestion run (or re-ingest of a stored video) completes with Qwen transcription when `TRANSCRIBE_PROVIDER=qwen`.
- Stretch, if attempted: one stored screenshot produces a correct Qwen-VL highlight box on a known object; one stored video produces a usable frame-sampled description.
- Full pytest suite passes with mocked providers (no live-key dependence in CI-style runs).
