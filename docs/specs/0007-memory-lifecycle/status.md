# 0007 Memory Lifecycle Status

## Status

Completed on July 18, 2026. Course-correction validation completed the same day.

## Verification Evidence

- Baseline before implementation: `conda run -n Project-Memoria python -m pytest tests/ -q` reported 87 passed with the two existing dependency warnings (Starlette/httpx and Python `audioop`).
- Superseded evidence: the earlier recorded result of 103 passed did **not** reproduce for the user. Sandbox-created ACL-locked `Storage/pytest-tmp` and `.pytest_cache` directories caused `WinError 5: Access is denied` in all 10 tests using `tmp_path`, leaving 93 passed plus 10 errors. This was environmental damage, not a 0007 implementation defect.
- Superseding required suite: after the user removed the locked directories and the basetemp fallback was hardened, `conda run -n Project-Memoria python -m pytest tests/ -q` reported **107 passed, zero failures, and zero errors**, with the same two dependency warnings, in 17.21 seconds. Conda emitted its existing non-fatal missing OpenCL vendor temp-file message after pytest exited successfully.
- Focused course-correction regression run: the lifecycle, hardening, and rehearsal-guard tests reported 20 passed. Coverage now includes refusal before a Mongo client call, pin/unpin non-subset skipping, deterministic suffixed summaries with no-op reruns, and basetemp fallback.
- Static validation: `node --check UI/script.js`, PowerShell rehearsal parsing, Python compile-all, and `git diff --check` passed.
- Superseding isolated live Qwen rehearsal: `powershell.exe -ExecutionPolicy Bypass -File scripts/run_spec0007_rehearsal.ps1` used MongoDB on port 27027 and `C:\tmp\spec0007-rehearsal\chroma`, never port 27017 or `Storage/chroma`, and removed its temporary stack. Its JSON evidence was:

```json
{
  "seeded_events": 6,
  "summary_day": "2026-07-14",
  "expected_summary_id": "sum_2026-07-14_0",
  "index_status": "rebuilt"
}
{
  "summary_id": "sum_2026-07-14_0",
  "summary_source_count": 3,
  "active_index_ids": [
    "spec0007-fresh-mug",
    "spec0007-low-1",
    "spec0007-pinned-survivor",
    "spec0007-stale-mug",
    "sum_2026-07-14_0"
  ],
  "summary_recall": true,
  "pinned_recall": true,
  "stale_similarity": 0.7252,
  "stale_final_score": 0.001756,
  "fresh_similarity": 0.5625,
  "fresh_final_score": 0.841166,
  "fresh_outranks_stale": true,
  "time_agent_raw_event_count": 4,
  "live_fall_importance": 0.9
}
{
  "first_consolidation": {
    "groups_formed": 1,
    "events_consolidated": 3,
    "summaries_created": 1,
    "failures": [],
    "skipped": []
  },
  "rerun_no_op": true,
  "pin_reactivated": true,
  "semantic_route": "semantic",
  "recall_debug_packed": 5,
  "summary_grounded_answer": "I remember that on the morning of July 14th, around 9:00 AM, you were in your bedroom quietly sorting your books and reading the morning newspaper. The summary for that day also notes that you made tea and watered your bedroom plant.",
  "ui_url": "http://127.0.0.1:8017"
}
```

- Browser rendering evidence was not rerun during the course correction. The independently verified desktop/mobile evidence remains valid: the panel began collapsed as `Memory used (3 of 4 considered)`, expanded to three fact/event/summary rows, preserved the pinned label, had no mobile horizontal overflow, and produced no browser-console errors. Temporary screenshots remain outside the repository under `C:\tmp`.
- Safety/data isolation: live rehearsal records were written only to the temporary MongoDB and Chroma stores; source events were archived through consolidation and never erased.
- Implementation commit: `d0c80c9` (`Implement spec 0007 memory lifecycle`).
- Course-correction implementation and superseding evidence are recorded in the course-correction commit associated with this status update.
