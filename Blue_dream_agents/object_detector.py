from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

try:
    from .llm.model_registry import get_model_registry
    from .llm.strands_runtime import invoke_multimodal_structured, invoke_structured
    from .memory_schema import MemoryEvent, ROOMS, memory_event_from_mongo
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.strands_runtime import invoke_multimodal_structured, invoke_structured
    from memory_schema import MemoryEvent, ROOMS, memory_event_from_mongo


logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    found: bool = Field(description="Whether the object was found")
    room_number: Optional[int] = Field(default=None)
    room_name: Optional[str] = Field(default=None)
    matched_object: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    hint: Optional[str] = Field(default=None)
    highlighted_image_path: Optional[str] = Field(default=None)


class ObjectQueryIntent(BaseModel):
    object_name: str
    room_id: Optional[int] = None


class ObjectInventoryMatch(BaseModel):
    found: bool = False
    room_id: Optional[int] = None
    matched_object: Optional[str] = None


class ObjectVisionCheck(BaseModel):
    found: bool = False
    description: str = ""


class ObjectHintResult(BaseModel):
    hint: Optional[str] = None


MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
_mongo_client: Optional[AsyncIOMotorClient] = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGO_URI)
    return _mongo_client


async def close_clients():
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None


async def _get_latest_room_states() -> List[MemoryEvent]:
    collection = get_mongo_client().dementia_assistance.events
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$room_number", "latest_doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$latest_doc"}},
    ]

    room_states: List[MemoryEvent] = []
    async for doc in collection.aggregate(pipeline):
        room_states.append(memory_event_from_mongo(doc))
    return room_states


async def _get_recent_history(limit: int = 15) -> str:
    collection = get_mongo_client().dementia_assistance.events
    cursor = collection.find().sort("timestamp", -1).limit(limit)
    events = []
    async for doc in cursor:
        event = memory_event_from_mongo(doc)
        t_str = event.timestamp.strftime("%H:%M:%S")
        desc = event.video_description or "No description"
        events.append(f"[{t_str}] {event.room_name}: {desc}")

    return "\n".join(reversed(events))


async def _parse_query_intent(user_query: str) -> ObjectQueryIntent:
    registry = get_model_registry()
    prompt = (
        f"Query: {user_query}\n"
        f"Rooms: {json.dumps(ROOMS)}\n"
        "Extract the target object and optional room id if the user mentioned one."
    )
    return await invoke_structured(
        prompt=prompt,
        output_model=ObjectQueryIntent,
        system_prompt=(
            "You parse lost-object queries for a home monitoring assistant. "
            "If the room is unclear, leave room_id null."
        ),
        model_id=registry.router,
        structured_output_prompt="Return the object name and optional room id.",
        max_tokens=300,
    )


async def _batch_semantic_match(
    search_term: str, room_states: List[MemoryEvent]
) -> Optional[ObjectInventoryMatch]:
    inventory_map = {
        f"{room.room_name} (ID {room.room_number})": room.room_objects
        for room in room_states
        if room.room_objects
    }
    if not inventory_map:
        return None

    registry = get_model_registry()
    prompt = (
        f"Search term: {search_term}\n"
        f"Room inventories:\n{json.dumps(inventory_map, indent=2)}"
    )
    result = await invoke_structured(
        prompt=prompt,
        output_model=ObjectInventoryMatch,
        system_prompt=(
            "You decide whether a target object appears in any room inventory. "
            "Account for synonyms and return a room id only if the match is grounded."
        ),
        model_id=registry.synthesis,
        structured_output_prompt=(
            "Return found=true only when a reasonable synonym match exists. "
            "Provide the matching room id and the matched object string."
        ),
        max_tokens=300,
    )
    if result.found and result.room_id is not None and result.matched_object:
        return result
    return None


async def _check_image_worker(
    object_name: str, room: MemoryEvent
) -> Optional[Dict[str, Any]]:
    if not room.screenshot_path or not os.path.exists(room.screenshot_path):
        return None

    registry = get_model_registry()
    try:
        result = await invoke_multimodal_structured(
            text_prompt=(
                f"Check whether the image contains a visible '{object_name}' or a "
                "clear synonym. If found, describe where it is in one short sentence."
            ),
            image_path=room.screenshot_path,
            output_model=ObjectVisionCheck,
            system_prompt=(
                "You inspect room images for a lost-object assistant. Only mark found "
                "true when the object is visibly present."
            ),
            model_id=registry.vision,
            fallback_model_id=registry.vision_fallback,
            structured_output_prompt=(
                "Return found plus a concise grounded description. If the object is "
                "not visible, return found=false."
            ),
            max_tokens=300,
        )
    except Exception as exc:
        logger.warning(
            "Image inspection failed for room %s: %s", room.room_number, exc
        )
        return None

    if result.found:
        return {
            "room": room,
            "description": result.description or "Object visible in room.",
        }
    return None


async def _parallel_vision_search(
    object_name: str, room_states: List[MemoryEvent]
) -> Optional[Dict[str, Any]]:
    results = await asyncio.gather(
        *[_check_image_worker(object_name, room) for room in room_states]
    )
    for result in results:
        if result:
            return result
    return None


async def _get_object_hints(search_term: str) -> Optional[str]:
    history_text = await _get_recent_history(limit=20)
    if not history_text:
        return None

    registry = get_model_registry()
    result = await invoke_structured(
        prompt=(
            f"User is looking for: {search_term}\n"
            "Here is the recent room timeline:\n"
            f"{history_text}"
        ),
        output_model=ObjectHintResult,
        system_prompt=(
            "You infer likely locations for a missing household item from a room "
            "activity timeline. Offer one grounded hint if the timeline suggests one."
        ),
        model_id=registry.synthesis,
        structured_output_prompt=(
            "Return one short hint or null if the timeline does not support any hint."
        ),
        max_tokens=300,
    )
    return result.hint


async def _run_sam3_blocking(image_path, object_name):
    try:
        try:
            from .sam3_api import sam3_api
        except ImportError:
            from sam3_api import sam3_api

        return await sam3_api(image_path, object_name)
    except ImportError:
        logger.warning("SAM3 module not found.")
        return None, None


async def _highlight_object(
    object_name: str, image_path: str, output_dir: str = "Storage/highlighted"
) -> Optional[str]:
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    try:
        result_image, scores = await _run_sam3_blocking(image_path, object_name)
        if scores is None:
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(ch for ch in object_name if ch.isalnum())
        output_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.png")
        result_image.save(output_path)
        return output_path
    except Exception as exc:
        logger.warning("Highlight failed for %s: %s", object_name, exc)
        return None


async def search_for_object(user_query: str) -> SearchResult:
    try:
        room_states = await _get_latest_room_states()
        if not room_states:
            return SearchResult(
                found=False, description="No monitoring data available."
            )

        parsed = await _parse_query_intent(user_query)
        target_object = parsed.object_name or user_query
        target_room_id = parsed.room_id

        rooms_to_search = room_states
        if target_room_id is not None:
            rooms_to_search = [
                room for room in room_states if room.room_number == int(target_room_id)
            ]
            if not rooms_to_search:
                return SearchResult(
                    found=False, description=f"Room {target_room_id} has no data."
                )

        inventory_match = await _batch_semantic_match(target_object, rooms_to_search)
        if inventory_match:
            room = next(
                (
                    room_state
                    for room_state in rooms_to_search
                    if room_state.room_number == inventory_match.room_id
                ),
                None,
            )
            if room:
                highlight_path = await _highlight_object(
                    inventory_match.matched_object or target_object,
                    room.screenshot_path,
                )
                return SearchResult(
                    found=True,
                    room_number=room.room_number,
                    room_name=room.room_name,
                    matched_object=inventory_match.matched_object,
                    description=f"Found {inventory_match.matched_object} in the {room.room_name}.",
                    highlighted_image_path=highlight_path,
                )

        vision_match = await _parallel_vision_search(target_object, rooms_to_search)
        if vision_match:
            room = vision_match["room"]
            highlight_path = await _highlight_object(target_object, room.screenshot_path)
            return SearchResult(
                found=True,
                room_number=room.room_number,
                room_name=room.room_name,
                matched_object=target_object,
                description=vision_match["description"],
                highlighted_image_path=highlight_path,
            )

        hint = await _get_object_hints(target_object)
        return SearchResult(
            found=False,
            description=f"Could not find '{target_object}' in any room.",
            hint=hint,
        )
    except Exception as exc:
        logger.exception("Object search failed.")
        return SearchResult(
            found=False, description=f"System error during search: {exc}"
        )


async def run_object_query(query: str) -> SearchResult:
    return await search_for_object(query)


if __name__ == "__main__":

    async def main():
        print("Running Object Detector Test...")
        result = await run_object_query("Where is my white story book?")
        print(result.model_dump())
        await close_clients()

    asyncio.run(main())
