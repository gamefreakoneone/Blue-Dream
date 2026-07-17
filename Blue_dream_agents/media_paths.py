"""Canonical conversions between stored, filesystem, and URL media paths."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_configured_media_root = (os.environ.get("MEDIA_ROOT") or "").strip()
MEDIA_ROOT = (
    Path(_configured_media_root).expanduser().resolve()
    if _configured_media_root
    else PROJECT_ROOT
)

_MOUNTS = {"storage": "Storage", "capture": "Capture"}
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:$")


def _path_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        text = os.fspath(value)
    except TypeError:
        text = str(value)
    text = str(text).strip().replace("\\", "/")
    return text or None


def _relative_parts(parts: list[str]) -> list[str]:
    cleaned: list[str] = []
    for part in parts:
        if not part or part == "." or _WINDOWS_DRIVE.match(part):
            continue
        if part == "..":
            if cleaned:
                cleaned.pop()
            continue
        cleaned.append(part)
    return cleaned


def normalize_stored_path(raw: Any) -> str | None:
    """Normalize legacy paths into a portable project-root-relative form."""

    text = _path_text(raw)
    if text is None:
        return None

    parts = [part for part in text.split("/") if part]
    for index, part in enumerate(parts):
        canonical_mount = _MOUNTS.get(part.casefold())
        if canonical_mount:
            tail = _relative_parts(parts[index + 1 :])
            return "/".join([canonical_mount, *tail])

    cleaned = _relative_parts(parts)
    return "/".join(cleaned) or None


def to_stored_path(path: Any) -> str | None:
    """Convert an absolute, relative, or legacy media path to stored form."""

    return normalize_stored_path(path)


def to_fs_path(stored: Any) -> Path | None:
    """Resolve a stored media path to an absolute path below ``MEDIA_ROOT``."""

    normalized = normalize_stored_path(stored)
    if normalized is None:
        return None
    return MEDIA_ROOT.joinpath(*normalized.split("/"))


def to_url_path(stored: Any) -> str | None:
    """Convert a stored media path to its FastAPI static-mount URL."""

    normalized = normalize_stored_path(stored)
    if normalized is None:
        return None

    parts = normalized.split("/")
    mount = _MOUNTS.get(parts[0].casefold())
    if mount is None:
        return None
    suffix = "/".join(parts[1:])
    return f"/{mount.casefold()}" + (f"/{suffix}" if suffix else "")


def resolve_output_dir(stored_dir: str) -> Path:
    """Resolve and create a project-root-relative media output directory."""

    output_dir = to_fs_path(stored_dir)
    if output_dir is None:
        raise ValueError("A non-empty stored output directory is required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
