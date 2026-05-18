from __future__ import annotations

import json
from typing import Any, Iterable


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
