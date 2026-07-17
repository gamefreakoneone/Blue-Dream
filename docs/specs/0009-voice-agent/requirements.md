# 0009 Voice Agent Requirements

## Goal

Let the patient talk to Memoria instead of typing, and hear it answer. Server-side speech-to-text and text-to-speech endpoints backed by the provider layer (DashScope for the Qwen submission), with a mic button in the web chat and a graceful fallback ladder: provider ASR/TTS → browser Web Speech API → text-only.

## Functional Requirements

### Backend

- `POST /voice/transcribe` — accepts an audio blob (multipart or raw body; webm/opus from MediaRecorder, plus wav), returns `{"text": "..."}` via `client.transcribe_audio` under `TRANSCRIBE_PROVIDER`.
- `POST /voice/speak` — accepts `{"text": "..."}`, returns audio bytes (`audio/mpeg` or the provider's format, content-type set accordingly) via `client.synthesize_speech` under `TTS_PROVIDER`; provider model per the 0005 spike findings.
- `GET /voice/capabilities` — `{"transcribe": bool, "tts": bool}` reflecting configured providers, so the UI picks its ladder rung without failed requests.
- Errors return clean JSON errors (never raw exceptions); an unconfigured provider returns capability `false` rather than 500s.

### Web UI

- Mic button beside the chat input: hold-to-talk (or tap-to-start/tap-to-stop) using `MediaRecorder`; on stop, the audio posts to `/voice/transcribe`, the text lands in the input and submits through the existing chat flow.
- Assistant replies (including proactive messages, as a stretch) are spoken: response text posts to `/voice/speak` and plays; a speaker-toggle button persists the preference in `localStorage` (default ON when TTS capability exists).
- Fallback rung 2: when server capabilities are false, the mic button uses the browser's `SpeechRecognition`/`speechSynthesis` (Web Speech API) where available.
- Fallback rung 3: neither available → mic/speaker controls hidden; text chat unchanged.
- Visible states on the mic button: idle / recording / transcribing.

## Technical Constraints

- ASR/TTS calls go through `llm/client.py`; if DashScope needs the native SDK (per the 0005 spike), the helper lives in the llm package.
- Keep clips short: cap recording at `VOICE_MAX_SECONDS=30` client-side.
- TTS responses for long answers may be truncated to the first ~500 characters (speaking a wall of text is worse than a summary; note the truncation with an ellipsis).
- No streaming (request/response round-trips only) — hackathon-simple.

## Non-Requirements

- No wake word, no always-on listening (deliberate: privacy posture).
- No voice for the mobile app.
- No voice-specific conversation state; transcribed text enters the normal `/query` flow with the session id.

## Acceptance Criteria

- Speaking "where is my water bottle?" into the mic produces the same grounded answer (with image) as typing it, and the answer is spoken aloud.
- `GET /voice/capabilities` correctly reflects configuration; with providers unset, the browser-API rung engages (in Chrome) and text-only otherwise.
- Voice endpoints covered by contract tests (mocked provider calls): happy path, unconfigured provider, oversized/empty audio rejection.
- The demo beat works over LAN on the demo machine's browser (HTTPS/localhost requirement for mic permissions verified — localhost works; note the LAN caveat in status.md if demoing from another device).
