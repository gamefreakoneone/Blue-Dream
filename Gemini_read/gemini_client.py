"""Utilities for analyzing clips with the Gemini API."""

from __future__ import annotations

import json
import os
import time
from typing import Dict

from google import genai

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore


_POLL_INTERVAL_SECONDS = 5
_MODEL_NAME = "gemini-2.0-flash"


def _ensure_api_key() -> str:
    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError(
            "API_KEY environment variable is required to use the Gemini client."
        )
    return api_key


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

    if not os.path.exists(clip_path):
        raise FileNotFoundError(f"Clip does not exist: {clip_path}")

    api_key = _ensure_api_key()
    client = genai.Client(api_key=api_key)

    uploaded_file = client.files.upload(file=clip_path)

    while getattr(uploaded_file.state, "name", None) == "PROCESSING":
        time.sleep(_POLL_INTERVAL_SECONDS)
        uploaded_file = client.files.get(name=uploaded_file.name)

    state_name = getattr(uploaded_file.state, "name", None)
    if state_name != "ACTIVE":
        raise RuntimeError(f"File upload failed with state: {state_name}")

    strict_prompt = f"""
You are an assistant that analyzes short security camera clips.
Return a strict JSON object with the following structure:
{{
  "clip_id": string,
  "room": string,
  "summary": string,
  "actions": [string],
  "notable_events": [
    {{"timestamp": string, "description": string}}
  ]
}}
Use ISO 8601 timestamps or relative offsets if exact times are unavailable.
Clip metadata:
- clip_id: {clip_id}
- room: {room}
Respond with JSON only.
""".strip()

    response = client.models.generate_content(
        model=_MODEL_NAME,
        contents=[uploaded_file, strict_prompt],
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
