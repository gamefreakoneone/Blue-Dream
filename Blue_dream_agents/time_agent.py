from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

try:
    from .llm.model_registry import get_model_registry
    from .llm.strands_runtime import invoke_structured, invoke_text
    from .timezone_utils import LOCAL_TZ, now_local
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.strands_runtime import invoke_structured, invoke_text
    from timezone_utils import LOCAL_TZ, now_local


class ActivityEvent(BaseModel):
    timestamp: datetime.datetime
    room_number: int
    room_name: str
    video_description: str = ""
    audio_transcript: str = ""
    room_objects: List[str] = Field(default_factory=list)


class TimelineResult(BaseModel):
    success: bool = Field(description="Whether events were found")
    event_count: int = Field(description="Number of events found")
    time_range: str = Field(description="Human-readable time range queried")
    summary: str = Field(description="Digestible narrative of activities")


class TranscriptResult(BaseModel):
    success: bool = Field(description="Whether transcripts were found")
    transcript_count: int = Field(description="Number of transcripts found")
    time_range: str = Field(description="Human-readable time range queried")
    transcripts: List[str] = Field(default_factory=list)
    summary: str = Field(description="Summary of what was discussed")


class ActivityCheckResult(BaseModel):
    found: bool = Field(description="Whether the activity was found")
    keyword: str = Field(description="What was searched for")
    confidence: str = Field(description="Confidence level: high, medium, low")
    summary: str = Field(description="Summary of findings")


class TimeResult(BaseModel):
    response_type: Literal["timeline", "transcripts", "activity_check", "general"] = (
        "general"
    )
    text: str = Field(description="The main human-readable answer to display")
    data: Dict[str, Any] = Field(default_factory=dict, description="Raw structured data")


class TimeQueryPlan(BaseModel):
    intent: Literal["timeline", "transcripts", "activity_check", "general"] = (
        "general"
    )
    time_range: str = "today"
    room_name: Optional[str] = None
    activity: Optional[str] = None
    hours: int = 24


class ActivityEvidence(BaseModel):
    found: bool = False
    confidence: Literal["high", "medium", "low"] = "low"
    evidence: str = ""


MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
ROOMS: Dict[int, str] = {
    0: "Bedroom",
    1: "Living Room",
}
ROOM_NAME_TO_ID: Dict[str, int] = {v.lower(): k for k, v in ROOMS.items()}
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


def _parse_room_name(room_name: str) -> Optional[int]:
    room_lower = room_name.lower().strip()
    if room_lower in ROOM_NAME_TO_ID:
        return ROOM_NAME_TO_ID[room_lower]

    for name, room_id in ROOM_NAME_TO_ID.items():
        if room_lower in name or name in room_lower:
            return room_id

    try:
        return int(room_name)
    except ValueError:
        return None


def _build_time_filter(
    time_range: str,
) -> tuple[datetime.datetime, datetime.datetime, str]:
    now = now_local()
    time_range_lower = time_range.lower().strip()

    if time_range_lower == "yesterday":
        start = datetime.datetime.combine(
            now.date() - timedelta(days=1), datetime.time.min, tzinfo=LOCAL_TZ
        )
        end = datetime.datetime.combine(
            now.date() - timedelta(days=1), datetime.time.max, tzinfo=LOCAL_TZ
        )
        desc = "yesterday"
    elif time_range_lower == "today":
        start = datetime.datetime.combine(
            now.date(), datetime.time.min, tzinfo=LOCAL_TZ
        )
        end = now
        desc = "today"
    elif time_range_lower in ("recently", "recent"):
        start = now - timedelta(hours=3)
        end = now
        desc = "the last 3 hours"
    elif "hour" in time_range_lower:
        match = re.search(r"(\d+)", time_range_lower)
        hours = int(match.group(1)) if match else 3
        start = now - timedelta(hours=hours)
        end = now
        desc = f"the last {hours} hour{'s' if hours != 1 else ''}"
    elif "day" in time_range_lower:
        match = re.search(r"(\d+)", time_range_lower)
        days = int(match.group(1)) if match else 1
        start = now - timedelta(days=days)
        end = now
        desc = f"the last {days} day{'s' if days != 1 else ''}"
    else:
        try:
            date = datetime.datetime.strptime(time_range, "%Y-%m-%d")
            start = datetime.datetime.combine(
                date.date(), datetime.time.min, tzinfo=LOCAL_TZ
            )
            end = datetime.datetime.combine(
                date.date(), datetime.time.max, tzinfo=LOCAL_TZ
            )
            desc = date.strftime("%B %d, %Y")
        except ValueError:
            start = datetime.datetime.combine(
                now.date(), datetime.time.min, tzinfo=LOCAL_TZ
            )
            end = now
            desc = "today"

    return start, end, desc


async def _get_events(
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    room_number: Optional[int] = None,
    limit: int = 100,
) -> List[ActivityEvent]:
    collection = get_mongo_client().dementia_assistance.events
    query: Dict[str, Any] = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}
    if room_number is not None:
        query["room_number"] = room_number

    events: List[ActivityEvent] = []
    cursor = collection.find(query).sort("timestamp", 1).limit(limit)
    async for doc in cursor:
        timestamp = doc.get("timestamp", now_local())
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        timestamp_local = timestamp.astimezone(LOCAL_TZ)

        room_num = doc.get("room_number", 0)
        events.append(
            ActivityEvent(
                timestamp=timestamp_local,
                room_number=room_num,
                room_name=ROOMS.get(room_num, f"Room {room_num}"),
                video_description=doc.get("video_description", ""),
                audio_transcript=doc.get("audio_transcript", ""),
                room_objects=doc.get("room_objects", []),
            )
        )

    return events


async def _summarize_with_llm(
    events: List[ActivityEvent], user_query_context: str
) -> str:
    if not events:
        return "I couldn't find any recorded activities for that time."

    context_data = []
    for event in events:
        context_data.append(
            {
                "time": event.timestamp.strftime("%I:%M %p"),
                "room": event.room_name,
                "activity": event.video_description[:2000],
                "speech": event.audio_transcript[:2000],
            }
        )

    registry = get_model_registry()
    prompt = (
        f'Question: "{user_query_context}"\n'
        f"Event log:\n{json.dumps(context_data, indent=2)}\n\n"
        "Respond in 2-3 short sentences. Be warm, clear, and mention specific "
        "times or rooms when useful."
    )
    return await invoke_text(
        prompt=prompt,
        system_prompt=(
            "You are a compassionate memory assistant helping a dementia patient "
            "recall recent activity."
        ),
        model_id=registry.synthesis,
        max_tokens=500,
    )


async def get_activity_history(time_range: str) -> TimelineResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        events = await _get_events(start_dt, end_dt)
        if not events:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_desc,
                summary=f"I don't have any recorded activities for {time_desc}. "
                "This might mean the cameras weren't active or you were away.",
            )

        summary = await _summarize_with_llm(events, f"What was I doing {time_desc}?")
        return TimelineResult(
            success=True,
            event_count=len(events),
            time_range=time_desc,
            summary=summary,
        )
    except Exception as exc:
        return TimelineResult(
            success=False,
            event_count=0,
            time_range=time_range,
            summary=f"I'm sorry, I had trouble looking up your activities: {exc}",
        )


async def get_room_activity(
    room_name: str, time_range: str = "today"
) -> TimelineResult:
    try:
        room_id = _parse_room_name(room_name)
        if room_id is None:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_range,
                summary=f"I'm sorry, I don't recognize the room '{room_name}'. "
                f"I currently monitor: {', '.join(ROOM_NAME_TO_ID.keys())}.",
            )

        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        events = await _get_events(start_dt, end_dt, room_number=room_id)
        clean_room_name = ROOMS.get(room_id, room_name)
        if not events:
            return TimelineResult(
                success=False,
                event_count=0,
                time_range=time_desc,
                summary=(
                    f"I didn't see any activity in the {clean_room_name} during "
                    f"{time_desc}."
                ),
            )

        summary = await _summarize_with_llm(
            events, f"What was I doing in the {clean_room_name} during {time_desc}?"
        )
        return TimelineResult(
            success=True,
            event_count=len(events),
            time_range=time_desc,
            summary=summary,
        )
    except Exception as exc:
        return TimelineResult(
            success=False,
            event_count=0,
            time_range=time_range,
            summary=f"I'm sorry, I had trouble looking up room activity: {exc}",
        )


async def get_recent_transcripts(
    time_range: str = "recently", room_name: Optional[str] = None
) -> TranscriptResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(time_range)
        room_id = _parse_room_name(room_name) if room_name else None
        room_display = ""

        if room_name:
            if room_id is None:
                return TranscriptResult(
                    success=False,
                    transcript_count=0,
                    time_range=time_desc,
                    transcripts=[],
                    summary=f"I'm sorry, I don't recognize the room '{room_name}'. "
                    f"I currently monitor: {', '.join(ROOM_NAME_TO_ID.keys())}.",
                )
            room_display = f" in the {ROOMS.get(room_id, room_name)}"

        events = await _get_events(start_dt, end_dt, room_number=room_id)
        speech_events = [
            event
            for event in events
            if event.audio_transcript and len(event.audio_transcript.strip()) > 5
        ]
        if not speech_events:
            return TranscriptResult(
                success=False,
                transcript_count=0,
                time_range=time_desc,
                transcripts=[],
                summary=f"I didn't capture any conversations{room_display} during {time_desc}. "
                "Perhaps you were quiet or away from the microphones.",
            )

        transcripts = [
            f"[{event.timestamp.strftime('%I:%M %p')} - {event.room_name}] "
            f"{event.audio_transcript}"
            for event in speech_events
        ]
        registry = get_model_registry()
        prompt = (
            f"Transcripts from {time_desc}{room_display}:\n"
            + "\n".join(f"- {entry}" for entry in transcripts)
            + "\n\nSummarize the main topics kindly and clearly in 2-3 sentences."
        )
        summary = await invoke_text(
            prompt=prompt,
            system_prompt=(
                "You help a dementia patient remember what they were talking about. "
                "Be warm, concise, and grounded in the transcript."
            ),
            model_id=registry.synthesis,
            max_tokens=500,
        )
        return TranscriptResult(
            success=True,
            transcript_count=len(transcripts),
            time_range=time_desc,
            transcripts=transcripts,
            summary=summary,
        )
    except Exception as exc:
        return TranscriptResult(
            success=False,
            transcript_count=0,
            time_range=time_range,
            transcripts=[],
            summary=f"I'm sorry, I had trouble looking that up: {exc}",
        )


async def check_activity(activity: str, hours: int = 24) -> ActivityCheckResult:
    try:
        start_dt, end_dt, time_desc = _build_time_filter(f"last {hours} hours")
        events = await _get_events(start_dt, end_dt)
        if not events:
            return ActivityCheckResult(
                found=False,
                keyword=activity,
                confidence="low",
                summary=f"I don't have any recorded activities in {time_desc} "
                f"to check for '{activity}'.",
            )

        descriptions = []
        for event in events:
            if event.video_description or event.audio_transcript:
                descriptions.append(
                    f"[{event.timestamp.strftime('%I:%M %p')}] {event.room_name}: "
                    f"{event.video_description} {event.audio_transcript}".strip()
                )

        if not descriptions:
            return ActivityCheckResult(
                found=False,
                keyword=activity,
                confidence="low",
                summary=f"I have activity records but no detailed descriptions "
                f"to search for '{activity}'.",
            )

        registry = get_model_registry()
        prompt = (
            f'Activity to verify: "{activity}"\n'
            f"Records from {time_desc}:\n"
            + "\n".join(descriptions)
        )
        evidence = await invoke_structured(
            prompt=prompt,
            output_model=ActivityEvidence,
            system_prompt=(
                "You check whether a dementia patient likely performed a target "
                "activity. Consider synonyms and related phrasing. Return grounded "
                "evidence only."
            ),
            model_id=registry.synthesis,
            structured_output_prompt=(
                "Return whether the activity was found, the confidence level, and "
                "a short evidence string."
            ),
            max_tokens=500,
        )

        if evidence.found:
            if evidence.confidence == "high":
                summary = (
                    f"Yes, I found evidence that you {activity}. {evidence.evidence}"
                )
            else:
                summary = (
                    f"I found possible evidence that you may have {activity}. "
                    f"{evidence.evidence}"
                )
        else:
            summary = (
                f"I didn't find clear evidence of '{activity}' in {time_desc}. "
                "This doesn't mean it didn't happen. I might have missed it, or it "
                "may have happened outside monitored areas."
            )

        return ActivityCheckResult(
            found=evidence.found,
            keyword=activity,
            confidence=evidence.confidence,
            summary=summary,
        )
    except Exception as exc:
        return ActivityCheckResult(
            found=False,
            keyword=activity,
            confidence="low",
            summary=f"I'm sorry, I had trouble checking for that activity: {exc}",
        )


async def _plan_time_query(query: str) -> TimeQueryPlan:
    registry = get_model_registry()
    return await invoke_structured(
        prompt=query,
        output_model=TimeQueryPlan,
        system_prompt=(
            "You route dementia-memory questions into one of four intents: "
            "timeline, transcripts, activity_check, or general. "
            "Timeline is for activity history or room history. "
            "Transcripts is for what was said or discussed. "
            "Activity_check is for verifying whether a specific activity happened."
        ),
        model_id=registry.router,
        structured_output_prompt=(
            "Extract the intent, time range, optional room name, optional activity, "
            "and hours if the user is asking to verify an activity."
        ),
        max_tokens=300,
    )


async def run_time_query(query: str) -> TimeResult:
    try:
        plan = await _plan_time_query(query)
        if plan.intent == "transcripts":
            result = await get_recent_transcripts(
                time_range=plan.time_range,
                room_name=plan.room_name,
            )
            return TimeResult(
                response_type="transcripts",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        if plan.intent == "activity_check":
            activity = plan.activity or query
            result = await check_activity(activity=activity, hours=plan.hours)
            return TimeResult(
                response_type="activity_check",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        if plan.intent == "timeline":
            if plan.room_name:
                result = await get_room_activity(
                    room_name=plan.room_name,
                    time_range=plan.time_range,
                )
            else:
                result = await get_activity_history(time_range=plan.time_range)

            return TimeResult(
                response_type="timeline",
                text=result.summary,
                data=result.model_dump(mode="json"),
            )

        registry = get_model_registry()
        text = await invoke_text(
            prompt=query,
            system_prompt=(
                "You are a kind memory assistant for a dementia patient. "
                "Answer briefly and do not promise unsupported features."
            ),
            model_id=registry.synthesis,
            max_tokens=300,
        )
        return TimeResult(response_type="general", text=text, data={})
    except Exception as exc:
        return TimeResult(
            response_type="general",
            text=f"I'm sorry, I had trouble answering that: {exc}",
            data={},
        )


if __name__ == "__main__":

    async def main():
        print("Running Time Agent Test...")
        result = await run_time_query("What was I talking about yesterday?")
        print(result.model_dump())
        await close_clients()

    asyncio.run(main())
