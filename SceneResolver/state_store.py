"""Persistence helpers for the scene resolver."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schemas import SceneState

STATE_PATH = Path("SceneResolver/state.json")


def load_state(path: Path = STATE_PATH) -> SceneState:
    """Load the persisted scene state from disk."""

    if not path.exists():
        return SceneState()

    try:
        raw: Any
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return SceneState()

    try:
        return SceneState.parse_obj(raw)
    except ValidationError:
        return SceneState()


def save_state(state: SceneState, path: Path = STATE_PATH) -> None:
    """Persist the provided scene state to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = state.json(indent=2, sort_keys=True)
    path.write_text(serialised, encoding="utf-8")
