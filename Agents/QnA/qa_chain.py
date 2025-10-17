"""LangGraph-style question answering over scene state and transcripts."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from SceneResolver.state_store import load_state
from SceneResolver.schemas import Event, SceneState

from langgraph.graph import END, START, StateGraph


logger = logging.getLogger(__name__)

STATE_PATH = Path(os.environ.get("STATE_PATH", "./data/state.json")).expanduser()
TRANSCRIPTS_DIR = Path(
    os.environ.get("TRANSCRIPTS_DIR", STATE_PATH.parent / "transcripts")
).expanduser()
MAX_TRANSCRIPT_FILES = int(os.environ.get("TRANSCRIPTS_MAX_FILES", "5"))


@dataclass
class Transcript:
    path: Path
    text: str

    def citation(self) -> str:
        return f"transcript:{self.path.stem}"


@dataclass
class SourceChunk:
    text: str
    citation: str


def _load_scene_state_node(state: Dict[str, Any]) -> Dict[str, Any]:
    scene_state = load_state(STATE_PATH)
    return {"scene_state": scene_state}


def _load_transcripts_node(state: Dict[str, Any]) -> Dict[str, Any]:
    transcripts = _load_transcripts(TRANSCRIPTS_DIR, MAX_TRANSCRIPT_FILES)
    return {"transcripts": transcripts}


from langchain_core.documents import Document
from . import rag_utils

VECTOR_STORE_DIR = Path(os.environ.get("VECTOR_STORE_DIR", "./data/vector_store")).expanduser()
def _build_sources_node(state: Dict[str, Any]) -> Dict[str, Any]:
    scene_state: SceneState = state.get("scene_state", SceneState())
    transcripts: Sequence[Transcript] = state.get("transcripts", [])
    documents: List[Document] = []

    for chunk in _summarise_world_state(scene_state):
        documents.append(Document(page_content=chunk.text, metadata={"citation": chunk.citation}))

    for chunk in _summarise_timeline(scene_state.timeline):
        documents.append(Document(page_content=chunk.text, metadata={"citation": chunk.citation}))

    for transcript in transcripts:
        documents.append(Document(page_content=transcript.text, metadata={"citation": transcript.citation()}))

    vector_store = rag_utils.create_vector_store_from_documents(documents, str(VECTOR_STORE_DIR))
    return {"vector_store": vector_store}


def _answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question: str = state.get("question", "")
    vector_store = state.get("vector_store")

    if not vector_store:
        return {"answer": "I'm not sure yet.", "citations": []}

    results = vector_store.similarity_search(question, k=1)

    if results:
        answer_text = results[0].page_content
        citations = [results[0].metadata.get("citation", "")]
    else:
        answer_text = "I'm not sure yet."
        citations = []

    return {"answer": answer_text, "citations": citations}


def _load_transcripts(directory: Path, limit: int) -> List[Transcript]:
    if not directory.exists():
        return []

    paths = sorted(
        (p for p in directory.iterdir() if p.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    transcripts: List[Transcript] = []
    for path in paths[:limit]:
        try:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                text = _flatten_json_transcript(payload)
            else:
                text = path.read_text(encoding="utf-8")
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to read transcript file %s", path)
            continue

        text = text.strip()
        if text:
            transcripts.append(Transcript(path=path, text=text))
    return transcripts


def _flatten_json_transcript(payload: Any) -> str:
    if isinstance(payload, dict):
        if "messages" in payload and isinstance(payload["messages"], Iterable):
            parts: List[str] = []
            for message in payload["messages"]:
                if isinstance(message, Mapping):
                    role = message.get("role", "")
                    content = message.get("content", "")
                    parts.append(f"{role}: {content}".strip())
                else:
                    parts.append(str(message))
            return "\n".join(part for part in parts if part)
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, list):
        return "\n".join(_flatten_json_transcript(item) for item in payload)
    return str(payload)


def _summarise_world_state(scene_state: SceneState) -> List[SourceChunk]:
    chunks: List[SourceChunk] = []
    for person, data in scene_state.world_state.persons.items():
        if not isinstance(data, Mapping):
            continue
        parts: List[str] = [f"{person} last seen in room {data.get('room', '?')}"]
        if data.get("last_activity"):
            parts.append(f"last activity: {data['last_activity']}")
        if data.get("last_seen"):
            parts.append(f"at {data['last_seen']}")
        chunks.append(
            SourceChunk(
                text=", ".join(parts),
                citation=f"state:person:{person}",
            )
        )

    for obj, data in scene_state.world_state.objects.items():
        if not isinstance(data, Mapping):
            continue
        parts: List[str] = [f"{obj} in room {data.get('room', '?')}"]
        if data.get("location"):
            parts.append(f"location {data['location']}")
        if data.get("picked_by"):
            parts.append(f"picked by {data['picked_by']}")
        chunks.append(
            SourceChunk(
                text=", ".join(parts),
                citation=f"state:object:{obj}",
            )
        )

    if scene_state.timeline:
        summary = f"Timeline contains {len(scene_state.timeline)} events."
        chunks.append(SourceChunk(text=summary, citation="state:timeline_summary"))

    return chunks


def _summarise_timeline(timeline: Sequence[Event]) -> List[SourceChunk]:
    chunks: List[SourceChunk] = []
    for event in timeline[-20:]:
        desc = event.description or event.action
        label = f"timeline:{event.event_id}"
        chunks.append(SourceChunk(text=desc, citation=label))
    return chunks





def _build_graph():
    graph = StateGraph(dict)
    graph.add_node("load_state", _load_scene_state_node)
    graph.add_node("load_transcripts", _load_transcripts_node)
    graph.add_node("build_sources", _build_sources_node)
    graph.add_node("select_answer", _answer_node)
    graph.add_edge(START, "load_state")
    graph.add_edge("load_state", "load_transcripts")
    graph.add_edge("load_transcripts", "build_sources")
    graph.add_edge("build_sources", "select_answer")
    graph.add_edge("select_answer", END)
    return graph.compile()


_QA_PIPELINE = _build_graph()


def answer(question: str) -> Dict[str, Any]:
    question = question.strip()
    if not question:
        return {"answer": "", "citations": []}

    state: Dict[str, Any] = {"question": question}
    result = _QA_PIPELINE(state)
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
    }


__all__ = ["STATE_PATH", "TRANSCRIPTS_DIR", "answer"]
