# 0009 Voice Agent Tasks

## Prerequisites

- [ ] Spec 0005 completed — its spike findings determine the DashScope ASR/TTS call shapes.

## Implementation Tasks

- [ ] Complete `client.synthesize_speech` (qwen per spike; openai branch; none → NotConfigured) returning `(bytes, content_type)`.
- [ ] Extend `client.transcribe_audio` to accept uploaded bytes.
- [ ] Add `/voice/transcribe`, `/voice/speak` (with `TTS_MAX_CHARS` truncation), `/voice/capabilities` endpoints with clean errors and size limits.
- [ ] UI: `initVoice()` rung selection; mic button (MediaRecorder, 30s cap, three visual states); browser `SpeechRecognition` rung; speaker playback + persisted toggle; controls hidden on rung 3.
- [ ] Stretch: speak proactive bubbles when voice-out is on.
- [ ] Document `TTS_PROVIDER`, `LLM_TTS_MODEL`, `TTS_MAX_CHARS` in `.env.example`; README note on mic secure-context (localhost vs LAN).

## Tests

- [ ] `tests/test_voice.py`: capabilities permutations, transcribe happy/empty/oversized, speak happy/truncation/unconfigured.
- [ ] Full suite passes.

## Manual Checks

- [ ] Spoken object question → correct grounded answer with image → spoken reply (server rung).
- [ ] Speaker toggle persists across reloads.
- [ ] Providers unset → browser rung functions in Chrome; both unavailable → clean text-only UI.
- [ ] Mic permission denied → no errors, graceful degradation.
- [ ] Record the demo rung + any DashScope audio caveats in `status.md`.

## Wrap-Up

- [ ] Update `docs/FEATURE_STATUS.md` + `status.md` with evidence; commit.
