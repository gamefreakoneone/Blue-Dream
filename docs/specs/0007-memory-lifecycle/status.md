# 0007 Memory Lifecycle Status

## Status

Completed on July 18, 2026.

## Verification Evidence

- Baseline before implementation: `conda run -n Project-Memoria python -m pytest tests/ -q` reported 87 passed with the two existing dependency warnings (Starlette/httpx and Python `audioop`).
- Final required suite: `conda run -n Project-Memoria python -m pytest tests/ -q` reported 103 passed and the same two warnings in 21.82 seconds. Conda also emitted its existing non-fatal missing OpenCL vendor temp-file message after pytest exited successfully.
- Static validation: `node --check UI/script.js`, PowerShell rehearsal parsing, Python compile-all, and `git diff --check` passed.
- Isolated live Qwen rehearsal: `powershell.exe -ExecutionPolicy Bypass -File scripts/run_spec0007_rehearsal.ps1` used MongoDB on port 27027 and a temporary Chroma directory, then removed both. It consolidated three mundane July 14 bedroom events into `sum_2026-07-14_0`; the rerun was a no-op; pinning reactivated a source event; semantic recall included the summary and pinned event; a fresh event scored `0.841245` versus `0.001757` for an older, more similar event; `recall_debug` packed five memories; the time-agent still saw four raw events; and live importance scoring returned `0.9`.
- Browser rendering: a deterministic local smoke server was exercised with installed Chrome at desktop and mobile viewports. The panel began collapsed as `Memory used (3 of 4 considered)`, expanded to three fact/event/summary rows, preserved the pinned label, had no mobile horizontal overflow, and produced no browser-console errors. Temporary screenshots were kept outside the repository under `C:\tmp`.
- Safety/data isolation: live rehearsal records were written only to the temporary MongoDB and Chroma stores; source events were archived through consolidation and never erased.
- Implementation commit: `d0c80c9` (`Implement spec 0007 memory lifecycle`).
