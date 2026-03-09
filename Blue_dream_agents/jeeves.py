from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

try:
    from .llm.model_registry import get_model_registry
    from .llm.strands_runtime import invoke_structured, strands_tool
    from .object_detector import run_object_query
    from .time_agent import run_time_query
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.strands_runtime import invoke_structured, strands_tool
    from object_detector import run_object_query
    from time_agent import run_time_query


class JeevesResponse(BaseModel):
    """Unified response structure for the chatbot API."""

    response_type: Literal["search_result", "activity", "general"] = Field(
        default="general"
    )
    text: str = Field(description="The main human-readable answer to display")
    image_path: Optional[str] = Field(
        default=None,
        description="Path to highlighted image (only for object search results)",
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Raw structured data from the sub-agent if applicable",
    )


@strands_tool
async def time_agent_tool(query: str) -> dict:
    """Handle questions about past activities, history, or conversations."""

    return (await run_time_query(query)).model_dump(mode="json")


@strands_tool
async def object_detector_tool(query: str) -> dict:
    """Handle questions about finding lost physical objects."""

    return (await run_object_query(query)).model_dump(mode="json")


def _jeeves_system_prompt() -> str:
    return (
        "You are Jeeves, the main assistant for a dementia-support system.\n"
        "Use `time_agent_tool` for questions about past activities, what was said, "
        "or what happened in a room.\n"
        "Use `object_detector_tool` for questions about locating a physical item.\n"
        "For greetings or general chat, answer directly.\n"
        "Always return a JeevesResponse.\n"
        "- If the object tool found something, set response_type to search_result, "
        "copy the description into text, copy highlighted_image_path into image_path, "
        "and store the full tool payload in data.\n"
        "- If the time tool was used, set response_type to activity, set text from "
        "the tool text, and store the tool payload in data.\n"
        "- For general chat, set response_type to general and leave image_path/data null."
    )


async def run_single_query(query: str) -> JeevesResponse:
    try:
        registry = get_model_registry()
        response = await invoke_structured(
            prompt=query,
            output_model=JeevesResponse,
            system_prompt=_jeeves_system_prompt(),
            model_id=registry.synthesis,
            tools=[time_agent_tool, object_detector_tool],
            structured_output_prompt=(
                "Return a valid JeevesResponse that preserves the existing API contract."
            ),
            max_tokens=1200,
        )
        return response
    except Exception as exc:
        return JeevesResponse(
            response_type="general",
            text=f"I encountered an error: {exc}",
            image_path=None,
            data=None,
        )


async def run_demo_loop():
    print("Jeeves is online. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            response = await run_single_query(user_input)
            print(f"\nJeeves: {response.text}")
            if response.image_path:
                print(f"Image: {response.image_path}")
            print(f"[Response Type: {response.response_type}]")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as exc:
            print(f"An error occurred: {exc}")


if __name__ == "__main__":
    asyncio.run(run_demo_loop())
