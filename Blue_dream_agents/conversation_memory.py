from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Optional


MAX_SESSION_TURNS = 12
MAX_CONTEXT_CHARS = 4000
SESSION_TTL_SECONDS = 2 * 60 * 60


@dataclass
class ConversationTurn:
    user: str
    assistant: str
    response_type: str
    timestamp: float


@dataclass
class ConversationSession:
    turns: list[ConversationTurn]
    updated_at: float


_sessions: dict[str, ConversationSession] = {}
_lock = RLock()


def _normalize_session_id(session_id: Optional[str]) -> Optional[str]:
    if session_id is None:
        return None
    normalized = session_id.strip()
    return normalized or None


def _cleanup_expired(now: float) -> None:
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session.updated_at > SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def get_conversation_context(session_id: Optional[str]) -> str:
    """Return a compact text rendering of recent turns for a session."""

    normalized_id = _normalize_session_id(session_id)
    if normalized_id is None:
        return ""

    now = time.time()
    with _lock:
        _cleanup_expired(now)
        session = _sessions.get(normalized_id)
        if session is None:
            return ""
        session.updated_at = now
        turns = list(session.turns[-MAX_SESSION_TURNS:])

    lines: list[str] = []
    for index, turn in enumerate(turns, start=1):
        user_text = " ".join(turn.user.split())
        assistant_text = " ".join(turn.assistant.split())
        lines.append(f"Turn {index} user: {user_text}")
        lines.append(
            f"Turn {index} assistant ({turn.response_type}): {assistant_text}"
        )

    rendered = "\n".join(lines)
    if len(rendered) <= MAX_CONTEXT_CHARS:
        return rendered
    return rendered[-MAX_CONTEXT_CHARS:]


def append_conversation_turn(
    session_id: Optional[str],
    *,
    user: str,
    assistant: str,
    response_type: str,
) -> None:
    """Append one user/assistant exchange to a session if a session id is present."""

    normalized_id = _normalize_session_id(session_id)
    if normalized_id is None:
        return

    now = time.time()
    turn = ConversationTurn(
        user=user.strip(),
        assistant=assistant.strip(),
        response_type=response_type.strip() or "general",
        timestamp=now,
    )

    with _lock:
        _cleanup_expired(now)
        session = _sessions.setdefault(
            normalized_id,
            ConversationSession(turns=[], updated_at=now),
        )
        session.turns.append(turn)
        session.turns = session.turns[-MAX_SESSION_TURNS:]
        session.updated_at = now


def reset_conversation(session_id: Optional[str]) -> bool:
    normalized_id = _normalize_session_id(session_id)
    if normalized_id is None:
        return False

    with _lock:
        return _sessions.pop(normalized_id, None) is not None
