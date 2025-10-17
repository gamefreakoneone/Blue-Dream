from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from SceneResolver.state_store import load_state

from .qa_chain import STATE_PATH, answer

app = FastAPI(title="Scene QA")


class Question(BaseModel):
    question: str


def _resolve_web_root() -> Path:
    current = Path(__file__).resolve()
    root = current.parent.parent.parent
    return root / "web_min"


@app.get("/state")
def get_state() -> dict:
    state = load_state(STATE_PATH)
    return state.model_dump(mode="python")


@app.post("/ask")
def ask(question: Question) -> dict:
    prompt = question.question.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    return answer(prompt)


@app.get("/")
def serve_index() -> FileResponse:
    web_root = _resolve_web_root()
    index_file = web_root / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(index_file)
