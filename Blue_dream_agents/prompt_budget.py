from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field


class RecallCandidate(BaseModel):
    id: str
    type: Literal["event", "summary", "fact"]
    text: str
    timestamp: datetime
    similarity: float = 0.0
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    pinned: bool = False


class PackedRecall(RecallCandidate):
    final_score: float
    estimated_tokens: int


class RecallPack(BaseModel):
    included: list[PackedRecall] = Field(default_factory=list)
    excluded_count: int = 0
    considered_count: int = 0
    used_tokens: int = 0


def truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def compact_json_records(
    records: Iterable[dict[str, Any]],
    *,
    max_chars: int,
) -> list[dict[str, Any]]:
    """Keep records until their JSON rendering fits a prompt character budget."""

    compacted: list[dict[str, Any]] = []
    for record in records:
        candidate = [*compacted, record]
        rendered = json.dumps(candidate, ensure_ascii=False)
        if len(rendered) > max_chars:
            break
        compacted.append(record)
    return compacted


def _estimated_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _score(candidate: RecallCandidate, *, half_life_days: float, now: datetime) -> float:
    timestamp = candidate.timestamp
    if timestamp.tzinfo is None and now.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=now.tzinfo)
    age_days = max(0.0, (now - timestamp).total_seconds() / 86_400.0)
    return (
        max(0.0, candidate.similarity)
        * math.exp(-age_days / half_life_days)
        * (1.0 + candidate.importance)
    )


def pack_recall(
    candidates: list[RecallCandidate],
    *,
    token_budget: int,
    half_life_days: float,
    now: datetime,
) -> RecallPack:
    """Score and pack whole memories; pinned memories may overflow the budget."""

    if token_budget < 0:
        raise ValueError("token_budget must be non-negative")
    if half_life_days <= 0:
        raise ValueError("half_life_days must be greater than zero")

    scored = [
        PackedRecall(
            **candidate.model_dump(),
            final_score=_score(candidate, half_life_days=half_life_days, now=now),
            estimated_tokens=_estimated_tokens(candidate.text),
        )
        for candidate in candidates
    ]

    def pinned_key(item: PackedRecall) -> tuple[float, str]:
        return (-item.timestamp.timestamp(), item.id)

    pinned_facts = sorted(
        (item for item in scored if item.pinned and item.type == "fact"),
        key=pinned_key,
    )
    pinned_events = sorted(
        (item for item in scored if item.pinned and item.type == "event"),
        key=pinned_key,
    )
    other_pinned = sorted(
        (
            item
            for item in scored
            if item.pinned and item.type not in {"fact", "event"}
        ),
        key=pinned_key,
    )
    unpinned = sorted(
        (item for item in scored if not item.pinned),
        key=lambda item: (-item.final_score, -item.timestamp.timestamp(), item.id),
    )

    included = [*pinned_facts, *pinned_events, *other_pinned]
    used_tokens = sum(item.estimated_tokens for item in included)
    for item in unpinned:
        if used_tokens + item.estimated_tokens <= token_budget:
            included.append(item)
            used_tokens += item.estimated_tokens

    return RecallPack(
        included=included,
        excluded_count=len(scored) - len(included),
        considered_count=len(scored),
        used_tokens=used_tokens,
    )
