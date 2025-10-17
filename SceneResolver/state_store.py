"""Simple file-backed scene state persistence."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .schemas import SceneState

_STATE_PATH = Path(os.environ.get("STATE_PATH", "./data/state.json")).expanduser()


def _ensure_directory(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Directory creation failure will be caught when attempting to write.
        pass


def load_state(path: Optional[Path] = None) -> SceneState:
    """Load a scene state from disk."""

    target = Path(path) if path is not None else _STATE_PATH
    if not target.exists():
        return SceneState()

    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return SceneState()

    try:
        return SceneState.model_validate(payload)
    except Exception:
        return SceneState()


def save_state(state: SceneState, path: Optional[Path] = None) -> None:
    """Persist a scene state to disk."""

    target = Path(path) if path is not None else _STATE_PATH
    _ensure_directory(target)
    serialised = state.model_dump(mode="json", by_alias=False)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(serialised, handle, indent=2)


__all__ = ["load_state", "save_state"]
