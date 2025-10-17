"""Utilities for analyzing clips with the Gemini API."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

from google import genai

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore


_POLL_INTERVAL_SECONDS = 3
_MODEL_NAME = "gemini-2.5-flash"
_PROMPT = """Instruct: Return one JSON object only matching this schema:

{
  "clip_id": "string",
  "room": "A|B",
  "summary": "string",
  "people": [
    {
      "pid_hint": "string",
      "appearance": { "top": "string", "bottom": "string", "shoes": "string", "others": "string|null" },
      "activities": ["entered","picked","placed","exited","carry","handoff"]
    }
  ],
  "objects": [
    {
      "name": "string",
      "picked_by": "string|null",
      "pick_time_s": 0.0,
      "placed_at": "string|null",
      "place_time_s": 0.0,
      "exited_with": false,
      "uncertain": false
    }
  ],
  "audio": {
    "present": true,
    "transcript": "string",
    "utterances": [ { "start_s": 0.0, "end_s": 0.0, "text": "string" } ]
  }
}


Rules:

Use clear appearance descriptors (colors/patterns).

If no audio track, set audio.present=false and omit transcript.

Prefer zones like desk_left, shelf, door if obvious; else set uncertain:true."""

_CLIENT: Optional[genai.Client] = None


def _ensure_api_key() -> str:
    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError(
            "API_KEY environment variable is required to use the Gemini client."
        )
    return api_key


def _get_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is None:
        api_key = _ensure_api_key()
        _CLIENT = genai.Client(api_key=api_key)
    return _CLIENT


def _strip_code_fences(payload: str) -> str:
    text = payload.strip()
    if text.startswith("```"):
        # Remove the opening fence (``` or ```json)
        newline_index = text.find("\n")
        if newline_index != -1:
            text = text[newline_index + 1 :]
        else:
            text = ""
    if text.endswith("```"):
        text = text[: text.rfind("```")].rstrip()
    return text


def analyze_clip(clip_path: str, clip_id: str, room: str) -> Dict:
    """Analyze a video clip using the Gemini API.

    Args:
        clip_path: Path to the MP4 video on disk.
        clip_id: Identifier for the clip.
        room: Human readable room/location label for the clip.

    Returns:
        Parsed JSON response from Gemini augmented with clip metadata.
    """

    clip_path = str(clip_path)
    path = Path(clip_path)
    if not path.exists():
        raise FileNotFoundError(f"Clip does not exist: {clip_path}")

    client = _get_client()

    uploaded_file = client.files.upload(file=clip_path)

    while getattr(uploaded_file.state, "name", None) == "PROCESSING":
        time.sleep(_POLL_INTERVAL_SECONDS)
        uploaded_file = client.files.get(name=uploaded_file.name)

    state_name = getattr(uploaded_file.state, "name", None)
    if state_name != "ACTIVE":
        raise RuntimeError(f"File upload failed with state: {state_name}")

    response = client.models.generate_content(
        model=_MODEL_NAME,
        contents=[uploaded_file, _PROMPT],
    )

    if not getattr(response, "text", "").strip():
        raise RuntimeError("Empty response received from Gemini.")

    cleaned = _strip_code_fences(response.text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on API output
        raise RuntimeError("Failed to decode Gemini response as JSON.") from exc

    if isinstance(result, dict):
        result.setdefault("clip_id", clip_id)
        result.setdefault("room", room)
    return result
