# 0009 Voice Agent Design

## Contracts You Must Not Break

- `/query` flow untouched: voice input becomes text before entering it; the response pipeline doesn't know voice exists.
- Patient-facing error rules; capability-driven degradation instead of failing requests.

## Backend

### `client.synthesize_speech` (completes the 0003 stub)

- `TTS_PROVIDER=qwen`: use the model/call shape recorded in the 0005 spike (compatible-mode `audio.speech` if available; else the native `dashscope` helper). Return `(audio_bytes, content_type)`.
- `TTS_PROVIDER=openai`: `client.audio.speech.create(model="gpt-4o-mini-tts", voice=..., input=text)` (wired fully in 0012; implement the branch now, it's three lines with the SDK already present).
- `TTS_PROVIDER=none`: raise `NotConfiguredError` → capabilities report false.

### `client.transcribe_audio`

Already provider-switched (0003/0005). Extend to accept bytes + filename (not just a path) so the endpoint can pass the upload straight through; write to a temp file only if the provider SDK requires a file object.

### Endpoints (`api.py`)

```
POST /voice/transcribe   multipart "audio" -> {"text": str}         # 413 on > ~5MB; 422 on empty/undecodable
POST /voice/speak        {"text": str}     -> audio bytes, correct content-type; text truncated to TTS_MAX_CHARS (500)
GET  /voice/capabilities                    -> {"transcribe": bool, "tts": bool}
```

Capabilities = "provider configured and importable", computed cheaply (no live API call). Log-and-clean-error on provider failures.

## Web UI

### `UI/script.js`

- `initVoice()`: fetch `/voice/capabilities`; decide rung: `server` | `browser` (feature-detect `window.SpeechRecognition || webkitSpeechRecognition` and `speechSynthesis`) | `none`; render controls accordingly.
- Mic (server rung): `navigator.mediaDevices.getUserMedia({audio:true})` → `MediaRecorder` (`audio/webm`); tap-to-start/tap-to-stop with a 30s auto-stop; blob → `POST /voice/transcribe` → put text in input → reuse the existing submit path. Button states: idle 🎤 / recording (pulsing red) / transcribing (spinner).
- Mic (browser rung): `SpeechRecognition` with `lang` default `en-US`, same input-and-submit behavior.
- Speaker: after rendering an assistant message, if voice-out enabled → server rung: `POST /voice/speak`, play via `new Audio(URL.createObjectURL(blob))`; browser rung: `speechSynthesis.speak(new SpeechSynthesisUtterance(text))`. Toggle button 🔊/🔇 persisted in `localStorage.memoriaVoiceOut`.
- Stretch (skip freely): proactive bubbles from 0008 also speak when voice-out is on.
- Mic permission requires a secure context: localhost is fine; for LAN-IP demos from another device the mic rung silently degrades — document in README.

### `UI/index.html` / `styles.css`

Mic button in the input row; speaker toggle in the header; recording pulse animation.

## Fallback ladder (explicit)

1. **Server ASR/TTS** (DashScope for the Qwen submission; OpenAI models in 0012's profile).
2. **Browser Web Speech API** — if the 0005 spike killed DashScope audio or keys are absent.
3. **Text-only** — controls hidden, zero regression.

The rung is chosen at page load from capabilities + feature detection; no mid-session switching complexity.

## Env

`TTS_PROVIDER` (0003), `LLM_TTS_MODEL`, `TTS_MAX_CHARS=500` server-side; `VOICE_MAX_SECONDS=30` as a JS constant. Document in `.env.example`.

## Tests (`tests/test_voice.py`)

- `/voice/capabilities` reflects configuration permutations (monkeypatched settings).
- `/voice/transcribe` happy path (mocked `transcribe_audio`), empty upload 422, oversized 413.
- `/voice/speak` happy path (mocked bytes + content-type), truncation at `TTS_MAX_CHARS`, unconfigured → clean error.
- No live-provider dependence.

## Validation Commands

```powershell
conda run -n Project-Memoria python -m pytest tests/ -q
```

Live: with DashScope configured — speak an object question end-to-end (mic → transcript → grounded answer + image → spoken reply); toggle speaker off/on; unset TTS/ASR env → browser rung works in Chrome; block mic permission → graceful degradation. Record which rung the demo will use in `status.md`.
