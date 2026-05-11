from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

try:
    from .llm.model_registry import get_model_registry
    from .llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from .llm.strands_runtime import invoke_structured, invoke_text
    from .object_detector import run_object_query
    from .semantic_search import SemanticSearchResult, run_semantic_query
    from .time_agent import TimeWindowContext, get_time_window_context, run_time_query
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.prompt_context import (
        with_monitoring_evidence_context,
        with_patient_answer_context,
        with_patient_cctv_context,
    )
    from llm.strands_runtime import invoke_structured, invoke_text
    from object_detector import run_object_query
    from semantic_search import SemanticSearchResult, run_semantic_query
    from time_agent import TimeWindowContext, get_time_window_context, run_time_query


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


class QueryRoute(BaseModel):
    intent: Literal["object", "time", "semantic", "general"] = "general"
    reason: str = ""


class SemanticDecision(BaseModel):
    decision: Literal[
        "use_semantic_only",
        "use_semantic_plus_time_window",
        "use_direct_time_reasoning",
        "insufficient_evidence",
    ] = "insufficient_evidence"
    anchor_event_id: Optional[str] = None
    reason: str = ""


_SPEECH_RECALL_TERMS = (
    "talk",
    "talking",
    "said",
    "say",
    "saying",
    "discuss",
    "discussed",
    "discussing",
    "mention",
    "mentioned",
    "mentioning",
    "conversation",
    "transcript",
)
_TIME_REFERENCE_TERMS = (
    "today",
    "yesterday",
    "earlier",
    "recently",
    "tonight",
    "this morning",
    "this afternoon",
    "this evening",
)


def _build_activity_response(text: str, data: dict[str, Any]) -> JeevesResponse:
    return JeevesResponse(
        response_type="activity",
        text=text,
        image_path=None,
        data=data,
    )


def _looks_like_speech_recall(query: str) -> bool:
    query_lower = query.lower()
    return any(term in query_lower for term in _SPEECH_RECALL_TERMS)


def _has_time_reference(query: str) -> bool:
    query_lower = query.lower()
    if any(term in query_lower for term in _TIME_REFERENCE_TERMS):
        return True
    return any(char.isdigit() for char in query_lower)


def _deterministic_route(query: str) -> Optional[QueryRoute]:
    query_lower = query.lower()
    if _looks_like_speech_recall(query) and (
        _has_time_reference(query) or query_lower.startswith("did i talk")
    ):
        return QueryRoute(
            intent="time",
            reason="Transcript recall questions with a time reference use the time agent.",
        )
    return None


async def _route_query(query: str) -> QueryRoute:
    deterministic_route = _deterministic_route(query)
    if deterministic_route is not None:
        return deterministic_route

    registry = get_model_registry()
    return await invoke_structured(
        prompt=query,
        output_model=QueryRoute,
        system_prompt=with_patient_cctv_context(
            "You route user queries for a dementia-support assistant. "
            "Choose 'object' for misplaced physical item searches. "
            "Choose 'time' for explicit time ranges, dates, day words like today "
            "or yesterday, room history, timelines, activity history, or questions "
            "asking what the patient was doing during a period. "
            "Choose 'semantic' for fuzzy recall about what was said, discussed, "
            "wanted, or why something was mentioned when the user is not mainly "
            "asking for a timeline or activity history. "
            "Choose 'general' for greetings or normal assistant chat."
        ),
        model_id=registry.router,
        structured_output_prompt=(
            "Return the single best intent and a short reason. "
            "Prefer time for 'what was I doing today/yesterday/earlier/on DATE' "
            "and other activity-history questions. Prefer semantic for "
            "conversational memory questions like 'what did I say/discuss/mention' "
            "unless the user is clearly asking for a transcript over a day, date, "
            "or recent time range. Use time for 'what was I talking about today' "
            "and 'did I talk about X today'."
        ),
        max_tokens=300,
    )


def _semantic_prompt_matches(result: SemanticSearchResult) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for match in result.matches:
        matches.append(
            {
                "event_id": match.event_id,
                "score": match.score,
                "timestamp": match.timestamp,
                "room_name": match.room_name,
                "transcript_length": match.transcript_length,
                "audio_transcript": match.audio_transcript[:800],
                "video_description": match.video_description[:800],
                "semantic_text": match.semantic_text[:1200],
            }
        )
    return matches


def _semantic_answer_matches(result: SemanticSearchResult) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for match in result.matches:
        matches.append(
            {
                "timestamp": match.timestamp,
                "room_name": match.room_name,
                "audio_transcript": match.audio_transcript[:1200],
                "video_description": match.video_description[:1200],
                "semantic_text": match.semantic_text[:1500],
            }
        )
    return matches


async def _judge_semantic_retrieval(
    query: str, semantic_result: SemanticSearchResult
) -> SemanticDecision:
    registry = get_model_registry()
    semantic_payload = {
        "success": semantic_result.success,
        "index_status": semantic_result.index_status,
        "error_code": semantic_result.error_code,
        "match_count": semantic_result.match_count,
        "matches": _semantic_prompt_matches(semantic_result),
    }
    prompt = with_monitoring_evidence_context(
        f'User question: "{query}"\n'
        f"Semantic retrieval evidence:\n{json.dumps(semantic_payload, indent=2)}\n\n"
        "Decide whether the semantic evidence is trustworthy enough to answer "
        "directly, needs nearby time grounding, should defer to direct time "
        "reasoning, or is too weak overall."
    )
    return await invoke_structured(
        prompt=prompt,
        output_model=SemanticDecision,
        system_prompt=with_patient_cctv_context(
            "You are the retrieval judge for a dementia-support memory assistant. "
            "Choose use_semantic_plus_time_window when semantic hits are relevant "
            "but the final answer should be verified with nearby timeline or "
            "transcript evidence around one anchor event. "
            "Choose use_direct_time_reasoning when the semantic hits are weak, "
            "contradictory, or the question is fundamentally temporal. "
            "Choose use_semantic_only only when the semantic evidence is already "
            "specific and trustworthy. "
            "Choose insufficient_evidence when the supplied evidence is too weak to "
            "support any grounded answer. "
            "Only provide anchor_event_id when selecting use_semantic_plus_time_window "
            "and only if that event id appears in the supplied evidence."
        ),
        model_id=registry.synthesis,
        structured_output_prompt=(
            "Return the decision, optional anchor_event_id, and a short reason. "
            "Never invent an anchor event id."
        ),
        max_tokens=400,
    )


async def _synthesize_semantic_answer(
    query: str,
    semantic_result: SemanticSearchResult,
    *,
    decision: SemanticDecision,
    time_window: Optional[TimeWindowContext] = None,
) -> str:
    registry = get_model_registry()
    prompt_payload: dict[str, Any] = {
        "query": query,
        "semantic_matches": _semantic_answer_matches(semantic_result),
    }
    if time_window is not None:
        prompt_payload["time_window"] = {
            "success": time_window.success,
            "event_count": time_window.event_count,
            "time_range": time_window.time_range,
            "room_name": time_window.room_name,
            "summary": time_window.summary,
            "transcripts": time_window.transcripts,
            "events": [
                {
                    "timestamp": event.get("timestamp"),
                    "room_name": event.get("room_name"),
                    "video_description": event.get("video_description"),
                    "audio_transcript": event.get("audio_transcript"),
                }
                for event in time_window.events
            ],
        }

    return await invoke_text(
        prompt=with_monitoring_evidence_context(
            "Evidence bundle:\n" + json.dumps(prompt_payload, indent=2)
        ),
        system_prompt=with_patient_answer_context(
            "You are Jeeves, a grounded memory assistant for a dementia-support "
            "system. Synthesize a concise answer using only the supplied evidence. "
            "Prefer transcript evidence when it directly answers the user's question. "
            "Mention uncertainty when the evidence is partial. Do not invent reasons, "
            "times, or conversations that are not present in the evidence. Answer the "
            "question directly; do not describe why one event was selected."
        ),
        model_id=registry.synthesis,
        max_tokens=500,
    )


async def _handle_semantic_query(query: str) -> JeevesResponse:
    semantic_result = await run_semantic_query(query)
    decision = await _judge_semantic_retrieval(query, semantic_result)
    response_data: dict[str, Any] = {
        "route_intent": "semantic",
        "semantic": semantic_result.model_dump(mode="json"),
        "judge_decision": decision.model_dump(mode="json"),
        "fallback_used": False,
        "anchor_event_id": decision.anchor_event_id,
        "anchor_timestamp": None,
    }

    if decision.decision == "use_direct_time_reasoning":
        time_result = await run_time_query(query)
        response_data["fallback_used"] = True
        response_data["time"] = time_result.model_dump(mode="json")
        return _build_activity_response(time_result.text, response_data)

    if decision.decision == "insufficient_evidence":
        if semantic_result.success and semantic_result.text:
            text = semantic_result.text
        else:
            text = (
                "I couldn't find enough reliable memory evidence to answer that "
                "clearly right now."
            )
        return _build_activity_response(text, response_data)

    time_window: Optional[TimeWindowContext] = None
    if decision.decision == "use_semantic_plus_time_window":
        anchor_match = next(
            (
                match
                for match in semantic_result.matches
                if match.event_id == decision.anchor_event_id
            ),
            semantic_result.matches[0] if semantic_result.matches else None,
        )
        if anchor_match is None:
            response_data["judge_decision"]["decision"] = "insufficient_evidence"
            return _build_activity_response(
                "I couldn't find enough reliable evidence to ground that memory.",
                response_data,
            )

        response_data["anchor_event_id"] = anchor_match.event_id
        response_data["anchor_timestamp"] = anchor_match.timestamp
        time_window = await get_time_window_context(
            anchor_match.timestamp,
            query=query,
            room_name=anchor_match.room_name,
        )
        response_data["time_window"] = time_window.model_dump(mode="json")
        response_data["fallback_used"] = True

    final_text = await _synthesize_semantic_answer(
        query,
        semantic_result,
        decision=decision,
        time_window=time_window,
    )
    return _build_activity_response(final_text, response_data)


async def _handle_general_query(query: str) -> JeevesResponse:
    registry = get_model_registry()
    text = await invoke_text(
        prompt=query,
        system_prompt=with_patient_answer_context(
            "You are a kind, concise assistant for a dementia-support system. "
            "Answer naturally and do not promise unsupported features."
        ),
        model_id=registry.synthesis,
        max_tokens=300,
    )
    return JeevesResponse(
        response_type="general",
        text=text,
        image_path=None,
        data=None,
    )


async def run_single_query(query: str) -> JeevesResponse:
    try:
        route = await _route_query(query)
        if route.intent == "object":
            result = await run_object_query(query)
            response_text = (result.description or "").strip() or "I couldn't find that object."
            return JeevesResponse(
                response_type="search_result",
                text=response_text,
                image_path=result.highlighted_image_path,
                data={
                    "route_intent": route.intent,
                    "route_reason": route.reason,
                    "object": result.model_dump(mode="json"),
                },
            )

        if route.intent == "time":
            result = await run_time_query(query)
            return JeevesResponse(
                response_type="activity",
                text=result.text,
                image_path=None,
                data={
                    "route_intent": route.intent,
                    "route_reason": route.reason,
                    "time": result.model_dump(mode="json"),
                },
            )

        if route.intent == "semantic":
            response = await _handle_semantic_query(query)
            if response.data is None:
                response.data = {}
            response.data["route_reason"] = route.reason
            return response

        response = await _handle_general_query(query)
        response.data = {
            "route_intent": route.intent,
            "route_reason": route.reason,
        }
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
