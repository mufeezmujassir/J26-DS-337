"""Read-only, evidence-aware holiday and event context feature engine."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.categories import Category
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import EventAttractionLink, TourismEvent


class HolidayEventFeatureRequest(BaseModel):
    travel_date: date
    travel_time: time | None = None
    attraction_ids: list[int] = Field(min_length=1, max_length=100)
    # ``interests`` is the public API spelling.  The legacy descriptive
    # spelling remains accepted so clients can migrate without a break.
    interests: list[str] = Field(
        default_factory=list,
        max_length=25,
        validation_alias=AliasChoices("interests", "tourist_interests"),
    )


class HolidayEventFeature(BaseModel):
    attraction_id: int
    is_public_holiday: bool | None = None
    is_bank_holiday: bool | None = None
    is_poya_day: bool = False
    poya_name: str | None = None
    nearby_event_count: int | None = None
    matched_event_ids: list[int] = Field(default_factory=list)
    overlapping_event_ids: list[int] = Field(default_factory=list)
    event_match_status: str | None = None
    event_match_confidence: float | None = Field(default=None, ge=0, le=1)
    event_match_evidence: list[str] = Field(default_factory=list)
    event_proximity_km: float | None = None
    cultural_relevance_score: float | None = Field(default=None, ge=0, le=1)
    holiday_context_score: float | None = Field(default=None, ge=0, le=1)
    event_context_score: float | None = Field(default=None, ge=0, le=1)
    context_confidence: Literal["high", "medium", "low", "unknown"]
    evidence_sources: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    explanation: str


class HolidayEventFeatureResponse(BaseModel):
    travel_date: date
    features: list[HolidayEventFeature]
    ranking_changed: bool = False
    scope: str = "Read-only holiday/event feature preview. It does not alter recommendation ranking."


def _normalise(values: list[str]) -> set[str]:
    return {value.casefold().strip() for value in values if value and value.strip()}


def _religious_compatibility(categories: list[str]) -> float | None:
    values = _normalise(categories)
    if not values:
        return None
    return 0.6 if any(word in value for value in values for word in ("relig", "temple", "heritage", "buddh")) else 0.3


class HolidayEventContextFeatureService:
    """Loads holidays, events, categories, and verified links in batch queries."""
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(self, request: HolidayEventFeatureRequest) -> HolidayEventFeatureResponse:
        ids = sorted(set(request.attraction_ids))
        # Interpret a requested calendar date in the product's Sri Lanka
        # operating timezone; never depend on the container's local timezone.
        local_tz = ZoneInfo("Asia/Colombo")
        start = datetime.combine(request.travel_date, time.min, tzinfo=local_tz)
        end = datetime.combine(request.travel_date, time.max, tzinfo=local_tz)
        attractions = (await self.db.execute(select(Attraction).where(Attraction.id.in_(ids), Attraction.is_active.is_(True)))).scalars().all()
        by_id = {row.id: row for row in attractions}
        categories: dict[int, list[str]] = {item: [] for item in ids}
        category_rows = await self.db.execute(select(AttractionCategory.attraction_id, Category.name).join(Category, Category.id == AttractionCategory.category_id).where(AttractionCategory.attraction_id.in_(ids)))
        for attraction_id, name in category_rows:
            categories.setdefault(attraction_id, []).append(name)
        holidays = (await self.db.execute(select(Holiday).where(Holiday.event_date == request.travel_date))).scalars().all()
        events = (await self.db.execute(select(TourismEvent).where(TourismEvent.status.in_(["scheduled", "unknown"]), TourismEvent.start_datetime.is_not(None), TourismEvent.start_datetime <= end, or_(TourismEvent.end_datetime.is_(None), TourismEvent.end_datetime >= start)))).scalars().all()
        links = (await self.db.execute(select(EventAttractionLink.event_id, EventAttractionLink.attraction_id, EventAttractionLink.evidence_source, EventAttractionLink.verification_status, EventAttractionLink.matching_confidence).where(EventAttractionLink.attraction_id.in_(ids)))).all()
        linked: dict[int, list[tuple[int, str, str, float | None]]] = {item: [] for item in ids}
        for event_id, attraction_id, evidence, status, confidence in links:
            linked.setdefault(attraction_id, []).append((event_id, evidence, status, confidence))
        features = [self._feature(item, categories.get(item.id, []), holidays, events, linked.get(item.id, [])) for item in attractions]
        missing = [item for item in ids if item not in by_id]
        features.extend(HolidayEventFeature(attraction_id=item, context_confidence="unknown", uncertainty_flags=["attraction_not_found_or_inactive"], explanation="Attraction is unavailable for context evaluation.") for item in missing)
        return HolidayEventFeatureResponse(travel_date=request.travel_date, features=sorted(features, key=lambda item: item.attraction_id))

    @staticmethod
    def _feature(attraction: Attraction, categories: list[str], holidays: list[Holiday], events: list[TourismEvent], links: list[tuple[int, str, str, float | None]]) -> HolidayEventFeature:
        poya = next((item for item in holidays if item.is_poya), None)
        evidence = [item.source_url for item in holidays if item.source_url]
        flags: list[str] = []
        # Calendar source currently supplies page-level public/bank context,
        # not row-level classification. Do not elevate those booleans to facts.
        public_or_bank = any(item.is_public_holiday or item.is_bank_holiday for item in holidays)
        if public_or_bank:
            flags.append("holiday_public_bank_classification_page_level_uncertain")
        cultural = _religious_compatibility(categories) if poya else None
        holiday_score = cultural if poya else None
        explanations: list[str] = []
        if poya:
            explanations.append("Poya day detected for the selected date. Religious-cultural relevance may be higher, but crowd conditions and opening hours are not verified.")
        elif holidays:
            explanations.append("Holiday record detected, but individual public/bank classification is not verified from row-level source evidence.")
        else:
            explanations.append("No holiday or Poya record is stored for the selected date.")
        event_ids = [event.id for event in events]
        verified_links = [(event_id, evidence, confidence) for event_id, evidence, status, confidence in links if status == "verified" and event_id in event_ids]
        candidate_links = [(event_id, evidence, confidence) for event_id, evidence, status, confidence in links if status == "candidate" and event_id in event_ids]
        linked_ids = [event_id for event_id, _, _ in verified_links]
        candidate_ids = [event_id for event_id, _, _ in candidate_links]
        if events:
            evidence.extend(event.source_url for event in events if event.source_url)
            if linked_ids:
                explanations.append("A verified event-attraction link overlaps the selected date.")
            elif candidate_ids:
                flags.append("semantic_event_candidate_not_verified")
                explanations.append("A semantic event-attraction candidate overlaps the selected date, but it is not verified and does not affect geographic relevance.")
            else:
                flags.append("overlapping_events_have_no_verified_attraction_link")
                flags.append("event_location_unresolved_or_unmatched")
                explanations.append("An event overlaps the selected date, but its location has not been verified for this attraction; geographic relevance was not applied.")
        if attraction.latitude is None or attraction.longitude is None:
            flags.append("attraction_coordinates_missing")
        if not categories:
            flags.append("attraction_categories_missing")
        confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
        if linked_ids:
            confidence = "high"
        elif poya:
            confidence = "medium"
        elif holidays or events:
            confidence = "low"
        return HolidayEventFeature(
            attraction_id=attraction.id,
            # Explicitly unknown: existing page-level values cannot establish
            # a row-specific public/bank classification.
            is_public_holiday=None if public_or_bank else False,
            is_bank_holiday=None if public_or_bank else False,
            is_poya_day=bool(poya), poya_name=poya.poya_name if poya else None,
            nearby_event_count=len(linked_ids) if linked_ids else None,
            matched_event_ids=linked_ids, overlapping_event_ids=event_ids,
            event_match_status="verified" if linked_ids else ("candidate" if candidate_ids else None),
            event_match_confidence=max((value or 0.0 for _, _, value in verified_links or candidate_links), default=None),
            event_match_evidence=sorted({evidence for _, evidence, _ in verified_links or candidate_links}),
            # A verified identity link establishes relevance, not co-location.
            # TourismEvent has no verified geometry at this stage, so a distance
            # must remain unknown even for a verified event-attraction link.
            event_proximity_km=None,
            cultural_relevance_score=cultural, holiday_context_score=holiday_score,
            event_context_score=1.0 if linked_ids else None,
            context_confidence=confidence, evidence_sources=sorted(set(evidence)),
            uncertainty_flags=sorted(set(flags)), explanation=" ".join(explanations),
        )
