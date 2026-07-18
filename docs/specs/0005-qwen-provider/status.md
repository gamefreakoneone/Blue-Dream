# 0005 Qwen Provider Status

## Status

Completed 2026-07-18 in implementation commit `73de261`. Implementation,
mocked validation, the full provider spike, user-run textual routes, live Qwen
Chroma indexing, and genuine matched-triplet ingestion are complete.

## Spike Findings

- Base URL / account region: international compatible-mode endpoint
  (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) passed.
- Available models: `qwen3.7-plus`, `qwen3-vl-flash`, and `qwen3-vl-plus`
  all accepted live requests.
- JSON/thinking: `qwen3.7-plus` honored `json_object`; thinking was present by
  default and `enable_thinking: false` succeeded. Observed sample latency was
  3.68 s default versus 1.04 s with thinking disabled in the completing spike.
- Embeddings: `text-embedding-v4` honored `dimensions=1024`; batch 10 passed
  and batch 11 was rejected.
- Image/grounding: `qwen3-vl-plus` found the requested story book at normalized
  `[x1,y1,x2,y2] = [53,517,174,667]`. The production renderer produced a
  visually correct tight box around the book and excluded the nearby phone.
- Multi-image: two sequential images were accepted as capability evidence
  only. This is deliberately not a production video fallback.
- ASR/TTS: OpenAI `/audio/transcriptions` was not exposed. Compatible-mode
  `qwen3-asr-flash` accepted the `input_audio` payload and returned a non-empty
  transcript for the user-selected 53.2-second camera-2 recording. Native
  `qwen3-asr-flash-filetrans` also reached `SUCCEEDED`; no `dashscope` SDK pin
  is needed. `qwen3-tts-flash` returned an expiring audio URL through native HTTP.
- OSS/video: private upload, deduplication, and signing worked. The first
  0.30-second clip was correctly rejected by Qwen's two-second minimum. The
  replacement fixture is a genuine 33.9 MB, 15.45-second silent capture, which
  also validates why the OSS URL bridge is required over the 10 MB inline cap.

## Verification Evidence

- `conda run -n Project-Memoria python scripts/dashscope_spike.py` (first live
  pass): 8 checks passed; OSS URL video failed only because the initial genuine
  fixture was 0.30 seconds, below the documented model minimum. Output was
  sanitized; no credential or signed query was recorded.
- `conda run -n Project-Memoria python -m pytest tests/ -q`: **74 passed**, two
  dependency deprecation warnings, 2026-07-18.
- Targeted provider/OSS/spatial/persistence suite: **36 passed**.
- Completing spike fixture selected by the user:
  `camera_1_2026-01-15_16-52-28.mp4` for full video and
  `camera_1_2026-01-15_17-09-41.jpg` for the story-book box, plus
  `camera_2_2026-01-17_19-31-05.mp3` for ASR:
  **9 grouped checks passed, 0 failed in 169.6 seconds**. The 33.9 MB video was
  uploaded/deduplicated under its canonical `Storage/...` key and analyzed from
  a redacted presigned URL; no signed query or credential was recorded.
- Production structured-video validation returned the full patient action
  sequence (enter, read book, place book on bed, use phone, put on cap, leave),
  objects `book`, `smartphone`, `white baseball cap`, and `headphones`, with no
  hazard or uncertainty. Production Qwen highlight output:
  `Storage/highlighted/qwen_spec0005/storybook_20260718_135430.png`.
- Privacy-safe live `/query` checks passed: general greeting returned HTTP 200
  with `route_intent=general`; a future date with no matching records returned
  HTTP 200 with `route_intent=time` and the reassuring no-activity answer.
- The user ran the real textual `/query` and semantic-index commands locally;
  general, time, and grounded semantic routes worked. Read-only verification
  then confirmed `memory_events__qwen__text-embedding-v4__1024` with **42**
  records while the legacy `memory_events` sibling remained intact with **40**.
- Genuine matched-triplet ingestion inserted Mongo event
  `6a5bfb30d5533af854270f0a`. It contains the full Qwen video description, the
  matching Qwen audio transcript, and canonical `video_oss_key`
  `Storage/video_recordings/camera_1/camera_1_2026-01-15_16-52-28.mp4`.
- Per user direction, no Gemini media comparison was performed; its fallback
  remains covered by deterministic tests.
- Pre-demo reminder recorded in `README.md`: back up required evidence, then
  explicitly clear local MongoDB and Chroma data before the public demo. No data
  was cleared during this work.
- Implementation commit: `73de261` (`Implement spec 0005 Qwen provider`).
