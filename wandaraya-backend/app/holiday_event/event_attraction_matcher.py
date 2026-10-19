"""Read-only semantic candidate generation and safe candidate-link persistence."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction_categories import AttractionCategory
from app.models.categories import Category
from app.models.holiday_event import EventAttractionLink, TourismEvent

from .event_location_resolver import GeographicEvidence, resolve_event_location
from .llm_extraction import LLMExtractionResult, extract_with_groq

if TYPE_CHECKING:
    from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever


class SemanticRetriever(Protocol):
    async def search(self, db: AsyncSession, query: str, limit: int = 10): ...


class EventAttractionCandidate(BaseModel):
    event_id: int
    attraction_id: int
    attraction_name: str
    match_status: str = "CANDIDATE"
    semantic_similarity: float
    semantic_candidate_rank: int
    semantic_evidence_fields: list[str]
    category_compatibility: str = "unknown"
    geographic_distance_km: float | None = None
    matching_confidence: float = Field(ge=0, le=1)
    evidence_source_url: str
    explanation: str
    uncertainty_flags: list[str] = Field(default_factory=list)


class EventMatchingResult(BaseModel):
    event_id: int
    query: str
    location: GeographicEvidence
    proposed_category: str | None = None
    llm_status: str = "LLM_NOT_REQUESTED"
    llm_requests: int = 0
    candidates: list[EventAttractionCandidate] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _event_text(event: TourismEvent) -> str:
    labelled = {
        "title": event.title,
        "description": event.description,
        "venue": event.venue,
        "category": event.category,
        "organizer": event.organizer,
        "notes": event.event_notes,
    }
    return "\n".join(f"{key}: {value}" for key, value in labelled.items() if value)


def _category_compatibility(event_category: str | None, attraction_categories: list[str]) -> str:
    if not event_category or not attraction_categories:
        return "unknown"
    event_terms = set(event_category.casefold().replace("/", " ").replace("-", " ").split())
    attraction_terms = set(" ".join(attraction_categories).casefold().replace("/", " ").replace("-", " ").split())
    return "supported" if event_terms & attraction_terms else "not_supported"


class EventAttractionMatcher:
    """Semantic results are always candidates until independently verified."""
    def __init__(self, db: AsyncSession, retriever: SemanticRetriever | None = None):
        self.db = db
        # Avoid importing sentence-transformers until a real semantic lookup is
        # needed.  Tests can inject a deterministic retriever without loading BGE.
        if retriever is None:
            from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
            retriever = SemanticAttractionRetriever()
        self.retriever = retriever

    async def match_event(self, event: TourismEvent, *, max_candidates: int = 10, enable_llm: bool = False) -> EventMatchingResult:
        query = _event_text(event)
        location = resolve_event_location(event)
        llm: LLMExtractionResult | None = None
        proposed_category: str | None = None
        # Groq is opt-in and sees only stored, public source-derived event text.
        if enable_llm and not event.category:
            llm = await extract_with_groq(query, enabled=True)
            proposed_category = llm.accepted_fields.get("category")
            if proposed_category:
                query = f"{query}\nproposed category: {proposed_category}"
        result = EventMatchingResult(
            event_id=event.id,
            query=query,
            location=location,
            proposed_category=proposed_category,
            llm_status=llm.status if llm else "LLM_NOT_NEEDED_OR_NOT_REQUESTED",
            llm_requests=llm.request_count if llm else 0,
        )
        if not query.strip():
            result.errors.append("event_has_no_source_text_for_semantic_candidate_generation")
            return result
        try:
            matches = await self.retriever.search(self.db, query, limit=max_candidates)
        except RuntimeError as exc:
            result.errors.append(f"semantic_retrieval_unavailable:{exc}")
            return result
        candidate_ids = [match.attraction_id for match in matches]
        category_rows = await self.db.execute(
            select(AttractionCategory.attraction_id, Category.name)
            .join(Category, Category.id == AttractionCategory.category_id)
            .where(AttractionCategory.attraction_id.in_(candidate_ids))
        ) if candidate_ids else []
        attraction_categories: dict[int, list[str]] = {}
        for attraction_id, category_name in category_rows:
            attraction_categories.setdefault(attraction_id, []).append(category_name)
        event_category = event.category or proposed_category
        for rank, match in enumerate(matches, start=1):
            # Similarity is a retrieval signal, not an identity probability.
            confidence = max(0.0, min(1.0, float(match.score)))
            result.candidates.append(EventAttractionCandidate(
                event_id=event.id,
                attraction_id=match.attraction_id,
                attraction_name=match.name,
                semantic_similarity=float(match.score),
                semantic_candidate_rank=rank,
                semantic_evidence_fields=[field for field in ("title", "description", "venue", "category", "organizer", "notes") if getattr(event, field if field != "notes" else "event_notes")],
                category_compatibility=_category_compatibility(event_category, attraction_categories.get(match.attraction_id, [])),
                matching_confidence=confidence,
                evidence_source_url=event.source_url,
                explanation="Semantic retrieval candidate only; it has not been verified as an event venue, location, or attraction identity.",
                uncertainty_flags=["semantic_similarity_is_not_geographic_or_identity_proof", *location.uncertainty_flags],
            ))
        return result

    async def persist_candidates(self, result: EventMatchingResult) -> tuple[int, int]:
        """Persist candidates idempotently without weakening any verified link."""
        inserted = updated = 0
        candidate_ids = [candidate.attraction_id for candidate in result.candidates]
        existing_rows = (await self.db.execute(select(EventAttractionLink).where(
            EventAttractionLink.event_id == result.event_id,
            EventAttractionLink.relationship_type == "event_relevance",
            EventAttractionLink.attraction_id.in_(candidate_ids),
        ))).scalars().all() if candidate_ids else []
        existing_by_attraction = {item.attraction_id: item for item in existing_rows}
        for candidate in result.candidates:
            existing = existing_by_attraction.get(candidate.attraction_id)
            if existing and existing.verification_status == "verified":
                continue
            values = {
                "evidence_source": candidate.evidence_source_url,
                "verification_status": "candidate",
                "evidence_type": "semantic_candidate",
                "semantic_similarity": candidate.semantic_similarity,
                "geographic_distance_km": candidate.geographic_distance_km,
                "matching_confidence": candidate.matching_confidence,
                "explanation": candidate.explanation,
                "verification_timestamp": None,
            }
            if existing is None:
                self.db.add(EventAttractionLink(event_id=candidate.event_id, attraction_id=candidate.attraction_id, relationship_type="event_relevance", **values))
                inserted += 1
            elif (existing.semantic_similarity or -1.0) < candidate.semantic_similarity:
                for field, value in values.items():
                    setattr(existing, field, value)
                updated += 1
        await self.db.flush()
        return inserted, updated
