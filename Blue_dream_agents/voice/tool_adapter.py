from __future__ import annotations

import json
from typing import Any

try:
    from ..jeeves import run_single_query
except ImportError:
    from jeeves import run_single_query


QUERY_MEMORIA_TOOL_NAME = "query_memoria"
QUERY_MEMORIA_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The user's spoken request as a standalone text query.",
        }
    },
    "required": ["query"],
}


VOICE_SYSTEM_PROMPT = (
    "You are Memoria, a warm and concise voice assistant for a dementia-support "
    "system. For every intentional user request, always call the query_memoria "
    "tool with the user's spoken request rewritten as a standalone text query. "
    "Do not answer memory, object-finding, timeline, or assistant questions from "
    "your own knowledge when the tool can answer them. After the tool returns, "
    "respond naturally using only the tool result. If image_path is present in "
    "the tool result, mention that an image is displayed on screen. Keep spoken "
    "responses short, clear, and easy to follow."
)


def get_query_memoria_tool_spec() -> dict[str, Any]:
    return {
        "toolSpec": {
            "name": QUERY_MEMORIA_TOOL_NAME,
            "description": (
                "Runs a user request through the Memoria retrieval and reasoning "
                "system. Use this for greetings, memory questions, object-finding, "
                "and activity or conversation recall."
            ),
            "inputSchema": {"json": json.dumps(QUERY_MEMORIA_INPUT_SCHEMA)},
        }
    }


async def execute_query_memoria(tool_payload: Any) -> dict[str, Any]:
    payload = tool_payload
    if isinstance(tool_payload, str):
        payload = json.loads(tool_payload)

    if not isinstance(payload, dict):
        return {"error": "Tool input must be a JSON object."}

    query = str(payload.get("query", "")).strip()
    if not query:
        return {"error": "Tool input is missing a non-empty query string."}

    response = await run_single_query(query)
    return response.model_dump(mode="json")
