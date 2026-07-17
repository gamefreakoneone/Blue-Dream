# 0001 Cleanup And Hardening Design

## Contracts You Must Not Break

- `POST /query` request/response shape (`JeevesResponse`), `POST /conversation/reset`, alert endpoints, geofence endpoints, `/storage` + `/capture` static mounts.
- Consolidator behavior: partial video/audio failures still persist an event; duplicate `video_path` never creates a second Mongo insert.
- `Capture/trained-weights/best.pt` stays where it is (fall detection loads it).

## 1. Deletions

- `References/` and `Reference/` directories (untracked scratch/vendored reference code — verify untracked with `git status --ignored` before removing) and the empty `System/` directory.
- `Blue_dream_agents/Tools/dementia_email.py`: keep only what the fall-alert path uses — the Gmail auth bootstrap and `send_alert_email` (the styled HTML alert with inline screenshot). Delete the inbox-monitoring loop, reply-to-email, `get_recent_emails`, and the interactive `main()` (~lines 307–597). The module shrinks to roughly its first third.
- `Blue_dream_agents/jeeves.py`: remove the unused `run_semantic_query` import and the unused `decision` parameter of `_synthesize_semantic_answer`.
- Leave all `llm/` provider code (bedrock, strands, ollama_runtime) in place — spec 0003 deletes it together with its replacement so the app never passes through a broken intermediate state.

## 2. requirements.txt

Pin every current dependency to the installed version (`pip freeze` filtered to direct deps), and add:

- `tzdata` — `ZoneInfo("America/Los_Angeles")` fails on a clean Windows install without it (today it arrives only as a transitive accident via chromadb).
- `pytest` — for the new suite.

Keep `strands-agents` for now (deleted in 0003). Do not add `python-dotenv`; `llm/settings.py` has its own parser.

## 3. Patient-facing exception leaks

Replace embedded `{exc}` in patient-visible text with a fixed message and full server-side logging. Sites (line numbers approximate to current HEAD):

- `Blue_dream_agents/jeeves.py:561–568` — catch-all returns `text=f"I encountered an error: {exc}"`.
- `Blue_dream_agents/time_agent.py:727` — same pattern.
- `Blue_dream_agents/semantic_search.py:383` and `:462` — same pattern.
- `Blue_dream_agents/api.py` — any `HTTPException(detail=str(e))` becomes a generic detail.

Pattern:

```python
logger.exception("query handling failed")
return JeevesResponse(
    response_type="general",
    text="I'm having a little trouble remembering right now. Please try again in a moment.",
    image_path=None,
    data=None,
)
```

Add a module-level `logger = logging.getLogger(__name__)` where missing.

## 4. video_agent polling timeout

`Blue_dream_agents/video_agent.py` (~line 110):

```python
deadline = time.monotonic() + settings_timeout  # VIDEO_ANALYSIS_TIMEOUT_SECONDS, default 300
while myfile.state == "PROCESSING":
    if time.monotonic() > deadline:
        raise TimeoutError(f"Gemini file processing exceeded {settings_timeout}s")
    time.sleep(1)
    myfile = self.client.files.get(name=myfile.name)
```

Read `VIDEO_ANALYSIS_TIMEOUT_SECONDS` from env (module-level, same style as the file's existing env reads). The raised error flows into the existing retry/partial-persist handling in `consolidator.py` — verify a timeout still produces a partial event with the audio transcript preserved.

## 5. TIMEZONE env

`Blue_dream_agents/timezone_utils.py`:

```python
import os
from zoneinfo import ZoneInfo
LOCAL_TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/Los_Angeles"))
```

Document `TIMEZONE` in `.env.example`.

## 6. Lifespan migration

`Blue_dream_agents/api.py`: replace `@app.on_event("startup")` with a lifespan context manager passed to `FastAPI(lifespan=...)`, preserving the tolerant Mongo index setup (startup must not crash when Mongo is down).

## 7. pytest scaffold

New `tests/` directory at repo root:

- `tests/conftest.py` — ensures repo root on `sys.path`; provides a `TestClient` fixture for `Blue_dream_agents.api:app` with the LLM call surface monkeypatched (patch `jeeves.run_single_query` to return a canned `JeevesResponse`) so tests run without Ollama/Mongo where possible; Mongo-dependent startup is already failure-tolerant.
- `tests/test_api_contract.py` — asserts: legacy `{"query": ...}` body returns the four `JeevesResponse` keys; `{"query", "session_id"}` accepted; `/conversation/reset` returns `{"ok": true}`; a patched exception inside query handling produces the fixed patient-safe text (no `Traceback`, no exception class names in `text`).
- `tests/test_error_messages.py` — unit checks that the error paths in jeeves/time_agent/semantic_search return the fixed strings (import the handlers and drive the except paths with monkeypatched internals).

## Validation Commands

```powershell
conda run -n Project-Memoria python -m compileall -q Blue_dream_agents Capture
conda run -n Project-Memoria python -m pytest tests/ -q
conda run -n Project-Memoria python -c "from Blue_dream_agents.Tools.dementia_email import GmailAgent"  # fall path intact
```

Validation for this spec is offline-only (pytest + compileall + import checks) — no live LLM provider is available pre-0005 (Ollama is not installed; the legacy Bedrock/Nova config is deleted by 0003). The live `/query`-per-route smoke runs in spec 0005 on Qwen. Optional: if the legacy Nova credentials in the current `.env` still work, a pre-refactor live sanity check may be run, but it is not required.
