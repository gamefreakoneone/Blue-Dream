"""FastAPI application exposing the question answering helpers."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .qa_chain import SceneState, answer as qa_answer, load_scene_state

app = FastAPI(title="Scene QA")


class Question(BaseModel):
    question: str


def _resolve_web_root() -> Path:
    current = Path(__file__).resolve()
    root = current.parent.parent.parent
    return root / "web_min"


@app.get("/state")
def get_state() -> dict:
    state: SceneState = load_scene_state()
    return state.to_dict()


@app.post("/ask")
def ask(question: Question) -> dict:
    prompt = question.question.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    return qa_answer(prompt)


@app.get("/")
def serve_index() -> FileResponse:
    web_root = _resolve_web_root()
    index_file = web_root / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(index_file)
