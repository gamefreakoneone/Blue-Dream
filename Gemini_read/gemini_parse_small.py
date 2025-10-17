"""Example script showing how to call :func:`analyze_clip`."""

from __future__ import annotations

import json
import sys

from gemini_client import analyze_clip


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python gemini_parse_small.py <clip_path> <clip_id> <room>")
        sys.exit(1)

    clip_path, clip_id, room = sys.argv[1:4]
    result = analyze_clip(clip_path, clip_id, room)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
