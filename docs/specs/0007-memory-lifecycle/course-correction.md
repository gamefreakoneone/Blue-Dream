# 0007 Memory Lifecycle — Course Correction

Written July 18, 2026, after an independent audit of commits `d0c80c9` (implementation) and `3912cee` (evidence). This document is the work order for the follow-up session. Read it fully, along with this spec's `requirements.md` and `tasks.md`, before changing anything.

## What happened

The spec 0007 implementation is committed and a requirement-by-requirement audit found **all 15 spec requirements compliant** — importance scoring with the 0.5 fallback, read-time schema normalization, safety auto-pin, consolidation grouping/idempotency/failure isolation, Chroma-only removal with no MongoDB deletes in production code, time agent untouched, consolidate/pin endpoints, the semantic-only re-rank formula, budgeted packing, `recall_debug`, the UI panel, rebuild filtering, test coverage, and the AGENTS.md cross-cutting rules.

However, the recorded evidence ("103 passed") did **not reproduce** when the user re-ran the suite: they got **93 passed + 10 errors**, all `WinError 5: Access is denied` on `Storage\pytest-tmp` and `.pytest_cache`.

Root cause: the implementing session ran inside a sandbox whose restricted process created `Storage\pytest-tmp` and `.pytest_cache` with ACLs that lock out the normal user account (even `Get-Acl` fails as the user). `tests/conftest.py` (a spec **0003** change, not 0007) points pytest's `basetemp` at `Storage/pytest-tmp`, and the 10 erroring tests are exactly the 10 that use the `tmp_path` fixture. This is environmental damage, not a code defect.

The rest of the evidence is genuine and independently verified:

- The user's **own** run of `scripts/run_spec0007_rehearsal.ps1` passed end-to-end: 3 events consolidated into `sum_2026-07-14_0`, no-op rerun, pin reactivation, summary + pinned recall, fresh event outranking a staler higher-similarity one (final scores 0.841 vs 0.0018), `recall_debug` packing 5 memories, time agent seeing 4 raw events, live importance 0.9.
- UI screenshots (`C:\tmp\spec0007-ui-desktop.png`, `C:\tmp\spec0007-ui-mobile.png`) were inspected directly and show the "Memory used (3 of 4 considered)" collapsible panel with fact/event/summary rows, the pinned label, and score bars at both viewports, with no overflow.

## Human prerequisite (already scheduled — the user runs this, not the agent)

The locked directories require an elevated delete. From an **Administrator** PowerShell:

```powershell
takeown /f "C:\Users\amogh\Desktop\Project Memoria\Storage\pytest-tmp" /r /d y
takeown /f "C:\Users\amogh\Desktop\Project Memoria\.pytest_cache" /r /d y
icacls "C:\Users\amogh\Desktop\Project Memoria\Storage\pytest-tmp" /reset /t
icacls "C:\Users\amogh\Desktop\Project Memoria\.pytest_cache" /reset /t
Remove-Item -Recurse -Force "C:\Users\amogh\Desktop\Project Memoria\Storage\pytest-tmp"
Remove-Item -Recurse -Force "C:\Users\amogh\Desktop\Project Memoria\.pytest_cache"
```

The follow-up session must first verify both paths are absent or writable; if either is still access-denied, **stop and report** rather than working around it.

## Fix list (execute in order)

### 1. Rehearsal destructive-run guard (HIGH)

`scripts/spec0007_rehearsal.py` (seed step, around lines 66–70) runs `delete_many({})` on `events`, `memory_summaries`, and `profile_facts` against whatever `MONGODB_URI` resolves to, and forces a Chroma rebuild at whatever `CHROMA_PERSIST_DIR` resolves to. All isolation currently lives in the PowerShell wrapper (`run_spec0007_rehearsal.ps1` sets `mongodb://127.0.0.1:27027` and a temp Chroma dir). Run standalone — or with a `.env` pointing at production — the script would wipe the production `dementia_assistance` collections on port 27017 and rebuild `Storage/chroma` from the emptied database. This violates the AGENTS.md rule "Never write smoke-test data into production collections" in spirit.

Fix: before any destructive operation, the Python script must refuse to run unless **all** of the following hold:

- `SPEC0007_REHEARSAL_ALLOW_DESTRUCTIVE=1` is set in the environment,
- `MONGODB_URI` is explicitly set and does not point at port 27017 / the default URI,
- `CHROMA_PERSIST_DIR` is explicitly set to a non-default path (not `Storage/chroma`).

Update `run_spec0007_rehearsal.ps1` to set the opt-in flag. Add a pytest asserting the guard refuses under a default/production-like environment (no live Mongo needed — assert the refusal happens before any client call).

### 2. Consolidation "poison pill" on non-subset groups (MEDIUM)

`Blue_dream_agents/memory_lifecycle.py` (~lines 141–143): if a day/room already has a summary and the newly eligible events are **not** a subset of its `source_event_ids` — e.g. an event pinned during consolidation then unpinned later, or a late-arriving low-importance event — the group raises `ValueError` and fails on **every future run**, permanently, with no remediation path.

Fix: handle the non-subset case gracefully instead of failing forever. Skip the already-summarized events; if the remaining unconsolidated events alone still meet `CONSOLIDATION_MIN_EVENTS`, summarize them under a new deterministic suffixed id (`sum_{date}_{room}_1`, incrementing); otherwise report the group as **skipped** (distinct from a failure) in the consolidation report. Add tests covering the pin→unpin→late-event scenario and the suffixed-id path. Preserve idempotency: re-running after the fix must still be a no-op.

### 3. conftest basetemp resilience (environment hardening)

`tests/conftest.py` `pytest_configure`: if `Storage/pytest-tmp` exists but is not writable/creatable by the current user, fall back to pytest's default system-temp `basetemp` instead of letting 10 `tmp_path` tests error. A simple probe (create the dir and touch/remove a file inside a try/except) is sufficient. This prevents any future sandbox-ACL recurrence from masquerading as test failures.

### 4. Evidence refresh

- Run `conda run -n Project-Memoria python -m pytest tests/ -q` — must finish with **zero errors and zero failures** (103 tests plus any added above).
- Re-run `powershell.exe -ExecutionPolicy Bypass -File scripts/run_spec0007_rehearsal.ps1` — must pass end-to-end.
- Update this spec's `status.md`: state plainly that the earlier 103-passed evidence did not reproduce for the user because sandbox-created ACL-locked temp directories broke the 10 `tmp_path` tests, and that the new run supersedes it. Record the new pytest summary and rehearsal JSON.
- Flip spec 0007 back to `Completed` in `docs/FEATURE_STATUS.md`.
- Commit the course-correction as its own descriptive commit (implementation + docs in one change, per the repo's update rule).

## Deferred — known behaviors, do NOT fix now

Recorded so nobody "fixes" these mid-hackathon; they are acceptable at demo scale and some are intentional:

1. **Pinned items may overflow the recall token budget** (`prompt_budget.py`) — deliberate reading of "guaranteed inclusion"; combined with the removal of jeeves' old char-truncation, prompt size is unbounded only in a pathological many-pins case.
2. **Unused compound index** `lifecycle_status_1_pinned_1_importance_1_timestamp_1` (`db_client.py`) — `_eligible_events` filters in Python instead; harmless at current scale.
3. **Out-of-scope jeeves.py behavior changes** — anchor fallback now degrades to `use_semantic_only` instead of `insufficient_evidence`, and prompt char-truncation was removed. Both are coherent with the new summary/fact match types; keep them.
4. **Cosmetics** — the UI score bar saturates for `final_score > 1.0`; pinned non-matching items display `0.000`. Correct data, slightly odd visuals.

## Out of scope — do not redo

- Do **not** reimplement any part of spec 0007; the implementation is audited and compliant.
- Do **not** start spec 0008.
- Do **not** attempt browser or Chrome-extension UI checks; UI rendering evidence exists and has been independently verified.
- Never point tests or rehearsals at MongoDB port 27017 or `Storage/chroma`.
- Leave `.agents/` and `skills-lock.json` untouched.
