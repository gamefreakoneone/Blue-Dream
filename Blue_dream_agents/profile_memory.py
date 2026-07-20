from __future__ import annotations

import logging
import os
import hashlib
from typing import Any, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator

try:
    from .db_client import get_profile_facts_collection
    from .llm.client import invoke_structured
    from .llm.model_registry import get_model_registry
    from .timezone_utils import now_local, to_local
except ImportError:
    from db_client import get_profile_facts_collection
    from llm.client import invoke_structured
    from llm.model_registry import get_model_registry
    from timezone_utils import now_local, to_local


logger = logging.getLogger(__name__)
DEFAULT_MAX_ACTIVE_FACTS = 50


class ExtractedFact(BaseModel):
    category: Literal["person", "preference", "routine", "medical", "safety"]
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("fact text is required")
        return cleaned


class ProfileFactExtraction(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


class FactDedupDecision(BaseModel):
    action: Literal["add", "update", "skip"]
    target_fact_id: Optional[str] = None
    merged_text: Optional[str] = None


def _configured_max_active_facts() -> int:
    try:
        return max(
            1,
            int(
                os.getenv(
                    "PROFILE_MAX_ACTIVE_FACTS",
                    str(DEFAULT_MAX_ACTIVE_FACTS),
                )
            ),
        )
    except ValueError:
        logger.warning(
            "Invalid PROFILE_MAX_ACTIVE_FACTS; using default %d",
            DEFAULT_MAX_ACTIVE_FACTS,
        )
        return DEFAULT_MAX_ACTIVE_FACTS


def _turn_fingerprint(user_text: str) -> str:
    normalized = " ".join(user_text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def serialize_profile_fact(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized.pop("_id", None)
    for field in ("created_at", "updated_at", "archived_at"):
        value = serialized.get(field)
        if value is not None:
            serialized[field] = to_local(value).isoformat()
    return serialized


class ProfileMemoryService:
    def __init__(
        self,
        collection=None,
        *,
        max_active_facts: Optional[int] = None,
    ):
        self._injected_collection = collection
        self.max_active_facts = (
            max_active_facts
            if max_active_facts is not None
            else _configured_max_active_facts()
        )

    @property
    def collection(self):
        if self._injected_collection is not None:
            return self._injected_collection
        return get_profile_facts_collection()

    async def get_active_facts(self) -> list[dict[str, Any]]:
        cursor = self.collection.find({"status": "active"}).sort(
            [("pinned", -1), ("confidence", -1), ("created_at", 1)]
        )
        return [serialize_profile_fact(document) async for document in cursor]

    async def render_profile_block(self, *, include_pinned: bool = True) -> str:
        facts = await self.get_active_facts()
        if not include_pinned:
            facts = [fact for fact in facts if not fact.get("pinned")]
        if not facts:
            return ""
        lines = ["What you know about the patient:"]
        for fact in facts:
            pin_marker = " [pinned]" if fact.get("pinned") else ""
            lines.append(
                f"- ({fact.get('category', 'person')}) {fact.get('text', '')}{pin_marker}"
            )
        return "\n".join(lines)

    async def extract_and_store(
        self,
        user_text: str,
        assistant_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> ProfileFactExtraction:
        now = now_local()
        extraction = await invoke_structured(
            prompt={
                "now": now.isoformat(),
                "timezone": str(now.tzinfo),
                "user_message": user_text,
                "assistant_reply": assistant_text,
            },
            output_model=ProfileFactExtraction,
            system_prompt=(
                "Extract durable patient memory from one chat turn. Facts must be "
                "stable personal information only: people and relationships, "
                "preferences, routines, medical facts, or safety facts. Ignore "
                "transient states and assistant claims."
            ),
            model_id=get_model_registry().router,
            structured_output_prompt=(
                "Return only the durable profile facts found in this turn."
            ),
            max_tokens=600,
        )

        fingerprint = _turn_fingerprint(user_text)
        already_processed = await self.collection.find_one(
            {"status": "active", "source_fingerprints": fingerprint}
        )
        if already_processed is None:
            for fact in extraction.facts:
                try:
                    await self._deduplicate_and_store(
                        fact, source_fingerprint=fingerprint
                    )
                except Exception:
                    logger.exception(
                        "Profile fact persistence failed for category %s",
                        fact.category,
                    )

        await self._enforce_cap()
        return extraction

    async def _deduplicate_and_store(
        self,
        fact: ExtractedFact,
        *,
        source_fingerprint: Optional[str] = None,
    ) -> str:
        cursor = self.collection.find(
            {"status": "active", "category": fact.category}
        ).sort([("pinned", -1), ("confidence", -1)])
        existing = [document async for document in cursor]
        decision = await invoke_structured(
            prompt={
                "new_fact": fact.model_dump(mode="json"),
                "active_same_category_facts": [
                    {
                        "fact_id": document.get("fact_id"),
                        "text": document.get("text"),
                        "confidence": document.get("confidence"),
                        "pinned": document.get("pinned", False),
                    }
                    for document in existing
                ],
            },
            output_model=FactDedupDecision,
            system_prompt=(
                "Deduplicate durable patient profile facts. Skip facts that repeat "
                "the same information, update a supplied target when the new fact "
                "clarifies or corrects it, and add only genuinely distinct facts."
            ),
            model_id=get_model_registry().router,
            structured_output_prompt=(
                "For update, target_fact_id must be one of the supplied IDs and "
                "merged_text must contain the complete corrected fact."
            ),
            max_tokens=350,
        )

        if decision.action == "skip":
            return "skip"

        targets = {
            str(document.get("fact_id")): document for document in existing
        }
        target = targets.get(str(decision.target_fact_id))
        if decision.action == "update" and target is not None:
            merged_text = " ".join((decision.merged_text or fact.text).split())
            fingerprints = list(target.get("source_fingerprints") or [])
            if source_fingerprint and source_fingerprint not in fingerprints:
                fingerprints.append(source_fingerprint)
            await self.collection.update_one(
                {"fact_id": target["fact_id"], "status": "active"},
                {
                    "$set": {
                        "text": merged_text,
                        "confidence": max(
                            float(target.get("confidence", 0.0)), fact.confidence
                        ),
                        "source_fingerprints": fingerprints,
                        "updated_at": now_local(),
                    }
                },
            )
            return "update"

        object_id = ObjectId()
        now = now_local()
        await self.collection.insert_one(
            {
                "_id": object_id,
                "fact_id": str(object_id),
                "category": fact.category,
                "text": fact.text,
                "confidence": fact.confidence,
                "pinned": False,
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "source_fingerprints": (
                    [source_fingerprint] if source_fingerprint else []
                ),
            }
        )
        return "add"

    async def _enforce_cap(self) -> None:
        cursor = self.collection.find({"status": "active"})
        active = [document async for document in cursor]
        overflow = len(active) - self.max_active_facts
        if overflow <= 0:
            return
        candidates = sorted(
            (document for document in active if not document.get("pinned", False)),
            key=lambda document: (
                float(document.get("confidence", 0.0)),
                document.get("created_at") or now_local(),
            ),
        )
        for document in candidates[:overflow]:
            await self.collection.update_one(
                {"fact_id": document["fact_id"], "status": "active"},
                {
                    "$set": {
                        "status": "archived",
                        "archived_at": now_local(),
                        "updated_at": now_local(),
                    }
                },
            )

    async def pin(self, fact_id: str) -> bool:
        result = await self.collection.update_one(
            {"fact_id": fact_id, "status": "active"},
            {"$set": {"pinned": True, "updated_at": now_local()}},
        )
        return bool(result.matched_count)

    async def archive(self, fact_id: str) -> bool:
        now = now_local()
        result = await self.collection.update_one(
            {"fact_id": fact_id, "status": "active"},
            {
                "$set": {
                    "status": "archived",
                    "pinned": False,
                    "archived_at": now,
                    "updated_at": now,
                }
            },
        )
        return bool(result.matched_count)


_default_service = ProfileMemoryService()


async def extract_and_store(
    user_text: str,
    assistant_text: str,
    *,
    session_id: Optional[str] = None,
) -> ProfileFactExtraction:
    return await _default_service.extract_and_store(
        user_text, assistant_text, session_id=session_id
    )


async def get_active_facts() -> list[dict[str, Any]]:
    return await _default_service.get_active_facts()


async def render_profile_block() -> str:
    return await _default_service.render_profile_block()


async def render_unpinned_profile_block() -> str:
    return await _default_service.render_profile_block(include_pinned=False)


async def pin_fact(fact_id: str) -> bool:
    return await _default_service.pin(fact_id)


async def archive_fact(fact_id: str) -> bool:
    return await _default_service.archive(fact_id)
