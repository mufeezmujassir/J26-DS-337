"""Read-only, explainable experimental holiday/Poya/event context scoring."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction_categories import AttractionCategory
from app.models.categories import Category
from .context_features import HolidayEventContextFeatureService, HolidayEventFeatureRequest
from .scoring_config import load_scoring_config

class ContextScoreRequest(BaseModel):
    travel_date: date
    attraction_ids: list[int] = Field(min_length=1, max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=25)
    include_explanations: bool = True

class ContextScore(BaseModel):
    attraction_id: int
    holiday_score: float | None = None
    poya_score: float | None = None
    event_score: float | None = None
    interest_compatibility_score: float | None = None
    context_suitability_score: float | None = None
    context_confidence: str
    evidence_coverage: float
    eligible_features: list[str] = Field(default_factory=list)
    excluded_features: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    matched_interests: list[str] = Field(default_factory=list)
    unmatched_interests: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    explanation: str

class ContextScoreResponse(BaseModel):
    travel_date: date
    scoring_version: str
    experimental: bool = True
    scores: list[ContextScore]
    ranking_changed: bool = False

def _norm(value: str) -> set[str]:
    return {word for word in value.casefold().replace("/", " ").replace("-", " ").split() if word}

class HolidayEventContextScoringService:
    def __init__(self, db: AsyncSession, config: dict | None = None):
        self.db, self.config = db, config or load_scoring_config()

    async def score(self, request: ContextScoreRequest) -> ContextScoreResponse:
        features = await HolidayEventContextFeatureService(self.db).evaluate(HolidayEventFeatureRequest(travel_date=request.travel_date, attraction_ids=request.attraction_ids, interests=request.interests))
        rows = await self.db.execute(select(AttractionCategory.attraction_id, Category.name).join(Category, Category.id == AttractionCategory.category_id).where(AttractionCategory.attraction_id.in_(request.attraction_ids)))
        categories: dict[int, list[str]] = {}
        for attraction_id, name in rows:
            categories.setdefault(attraction_id, []).append(name)
        return ContextScoreResponse(travel_date=request.travel_date, scoring_version=self.config["scoring_version"], scores=[self._score_feature(item, categories.get(item.attraction_id, []), request.interests) for item in features.features])

    def _score_feature(self, feature, categories: list[str], interests: list[str]) -> ContextScore:
        weights = self.config["feature_weights"]
        eligible: dict[str, float] = {}
        excluded, missing, flags = [], [], list(feature.uncertainty_flags)
        # Poya has a dependency on holiday evidence, so generic holiday scoring
        # is excluded on Poya days to prevent double counting the same evidence.
        if feature.is_poya_day:
            excluded.append("holiday:dependent_on_poya_evidence")
        elif feature.is_public_holiday is True or feature.is_bank_holiday is True:
            eligible["holiday"] = 0.5
        else:
            missing.append("verified_row_level_holiday_classification")
        if feature.is_poya_day and feature.cultural_relevance_score is not None:
            eligible["poya"] = feature.cultural_relevance_score
        elif feature.is_poya_day:
            missing.append("attraction_specific_cultural_metadata")
        else:
            excluded.append("poya:not_applicable")
        if feature.event_context_score is not None and feature.event_match_status == "verified":
            eligible["verified_event"] = feature.event_context_score
        elif feature.event_match_status == "candidate":
            excluded.append("verified_event:semantic_candidate_not_verified")
        else:
            missing.append("verified_event_attraction_evidence")
        normalized_interests = {item: _norm(item) for item in interests if item.strip()}
        category_terms = _norm(" ".join(categories))
        matched = sorted(name for name, terms in normalized_interests.items() if terms & category_terms)
        unmatched = sorted(set(normalized_interests) - set(matched))
        if normalized_interests and categories:
            eligible["interests"] = len(matched) / len(normalized_interests)
        elif normalized_interests:
            missing.append("attraction_category_metadata")
        else:
            excluded.append("interests:not_requested")
        numerator = sum(weights[name] * value for name, value in eligible.items())
        denominator = sum(weights[name] for name in eligible)
        final = round(numerator / denominator, 6) if denominator else None
        if not eligible:
            confidence = "INSUFFICIENT_EVIDENCE"
        elif "verified_event" in eligible:
            confidence = "HIGH"
        elif "poya" in eligible and "interests" in eligible:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        explanation = "Experimental weighted average of eligible evidence only." if final is not None else "No eligible context features; no neutral score was fabricated."
        return ContextScore(attraction_id=feature.attraction_id, holiday_score=eligible.get("holiday"), poya_score=eligible.get("poya"), event_score=eligible.get("verified_event"), interest_compatibility_score=eligible.get("interests"), context_suitability_score=final, context_confidence=confidence, evidence_coverage=round(len(eligible) / 4, 4), eligible_features=sorted(eligible), excluded_features=excluded, missing_features=sorted(set(missing)), matched_interests=matched, unmatched_interests=unmatched, evidence_sources=feature.evidence_sources, uncertainty_flags=sorted(set(flags)), explanation=explanation)
