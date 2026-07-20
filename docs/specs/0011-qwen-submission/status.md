# 0011 Qwen Submission Status

## Status

In progress.

## Verification Evidence

- Created the self-contained, accessible `Demo/memoria-architecture-qwen.svg` and rendered the matching 1800×1125 `Demo/memoria-architecture-qwen.png`.
- Audited the diagram against the implemented capture, ingestion, provider, memory, recall, proactive, push, and caretaker-alert paths. The graphic intentionally omits the unimplemented patient voice/TTS and ECS boundaries.
- SVG validation passed with `viewBox="0 0 1800 1125"`, one accessible title, one accessible description, eight unique IDs, no duplicate IDs, and no scripts, links, or external web resources.
- Headless Microsoft Edge produced an RGB 1800×1125 PNG. The raster was visually inspected at full size and as an 800×500 README-width preview with no clipped nodes or unreadable primary labels.
- Rehearsal logs exposed an exact-scope recall bug in the Mongo-direct time agent:
  explicit `morning`/`evening` wording was discarded, timeline synthesis replaced
  the exact question with a generic day question, and transcript synthesis was
  asked to summarize every topic. The minimal patch adds deterministic calendar
  day-part bounds, preserves the resolved question through synthesis, adds focused
  answer instructions to time and semantic recall, and logs plan/range/count only.
- Focused regression validation passed: **19 passed** across
  `test_time_query_scope.py`, `test_working_memory.py`, and
  `test_error_messages.py`. Coverage includes 06:00–12:00 morning and
  17:00–24:00 evening bounds, explicit-scope override, deterministic transcript
  planning, broad full-day preservation, exact-question propagation, and semantic
  fallback instructions.
- Full-suite validation with an isolated workspace-local pytest base reported
  **182 passed, 1 failed**. The sole failure is unrelated and predates this patch:
  the uncommitted `Capture/camera_feed.py` default confidence change from `0.50`
  to `0.75` conflicts with the existing two-box capture test. The recall patch's
  focused and dependent tests all pass; the unrelated user change was preserved.
- Privacy-safe live Qwen validation used synthetic records and no Mongo writes.
  `What did I do yesterday morning?` retrieved one 09:00 breakfast event and
  answered only: `Yesterday morning around 9:00 AM, you ate your breakfast in the
  living room.` The evening record was excluded by the computed time range.
  `What did I talk to my dad about yesterday evening?` supplied both a dad-call
  transcript and an unrelated later curry transcript; Qwen answered only that the
  patient would be home soon and bring gummy bears for the neighbors' kids, with no
  curry continuation. A real-data replay was intentionally not run because the
  execution environment blocked exporting local patient memories to an external
  provider; contextual UI confirmation remains a manual check.

The README rewrite, Devpost copy, full rehearsal, video, repository submission checks, tag, and Devpost submission remain pending.
