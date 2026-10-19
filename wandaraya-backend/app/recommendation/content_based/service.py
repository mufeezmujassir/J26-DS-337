"""Explainable, deterministic content-based attraction ranking.

This module reads Qdrant through the existing retriever and reads PostgreSQL
metadata.  It intentionally has no persistence behaviour.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.retrieval.semantic_retriever import (
    SemanticAttractionRetriever,
    SemanticCandidate,
)
from app.models.activities import Activity
from app.models.attraction import Attraction
from app.models.attraction_activities import AttractionActivity
from app.models.attraction_categories import AttractionCategory
from app.models.categories import Category
from app.models.district import District
from app.recommendation.content_based.schemas import (
    ContentBasedRecommendationItem,
    ContentBasedRecommendationRequest,
    ContentBasedRecommendationResponse,
)


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalised_set(values: Iterable[str]) -> set[str]:
    return {_normalise(value) for value in values if value and value.strip()}


def _name_matches(preference: str, stored_name: str) -> bool:
    """Match a complete normalized preference to a verified stored label.

    This supports safe label refinement such as ``Heritage`` matching the
    stored ``Culture & Heritage``.  It does not use fuzzy similarity or infer
    new activities; ``Walking`` therefore does not become ``Sightseeing``.
    """
    preferred_tokens = set(_normalise(preference).split())
    stored_tokens = set(_normalise(stored_name).split())
    return bool(preferred_tokens) and preferred_tokens.issubset(stored_tokens)


def _matching_stored_names(preferences: Iterable[str], stored_names: Iterable[str]) -> list[str]:
    stored = list(stored_names)
    return sorted(
        {name for preference in preferences for name in stored if _name_matches(preference, name)},
        key=_normalise,
    )


def _preference_ratio(preferences: Iterable[str], stored_names: Iterable[str]) -> float:
    clean_preferences = list(_normalised_set(preferences))
    available = list(stored_names)
    if not clean_preferences:
        return 0.0
    return sum(any(_name_matches(preference, name) for name in available) for preference in clean_preferences) / len(clean_preferences)


def _shift_cosine(raw_score: float) -> float:
    """Map a cosine-like score from [-1, 1] to [0, 1], not to probability."""
    return max(0.0, min(1.0, (raw_score + 1.0) / 2.0))


@dataclass(frozen=True)
class HydratedAttraction:
    attraction: Attraction
    category_names: tuple[str, ...]
    activity_names: tuple[str, ...]
    region_name: str | None = None


class ContentBasedRecommendationService:
    """Stage 12.1 read-only baseline service."""

    def __init__(
        self,
        db: AsyncSession | None,
        retriever: SemanticAttractionRetriever | None = None,
    ) -> None:
        self.db = db
        self.retriever = retriever or SemanticAttractionRetriever()

    @staticmethod
    def build_retrieval_query(request: ContentBasedRecommendationRequest) -> str:
        pieces = [request.interests.strip()]
        if request.travel_style:
            pieces.append(f"travel style: {request.travel_style.strip()}")
        if request.preferred_categories:
            pieces.append("categories: " + ", ".join(request.preferred_categories))
        if request.preferred_activities:
            pieces.append("activities: " + ", ".join(request.preferred_activities))
        return " | ".join(pieces)

    async def recommend(
        self, request: ContentBasedRecommendationRequest
    ) -> ContentBasedRecommendationResponse:
        if self.db is None:
            raise RuntimeError("A database session is required for content recommendations.")
        retrieval_query = self.build_retrieval_query(request)
        candidates = await self.retriever.search(
            db=self.db, query=retrieval_query, limit=request.candidate_pool_size
        )
        unique_candidates = self._deduplicate_candidates(candidates)
        hydrated = await self._hydrate([candidate.attraction_id for candidate in unique_candidates])
        return self.rank_hydrated(request, retrieval_query, unique_candidates, hydrated)

    @staticmethod
    def _deduplicate_candidates(candidates: list[SemanticCandidate]) -> list[SemanticCandidate]:
        best: dict[int, SemanticCandidate] = {}
        for candidate in candidates:
            prior = best.get(candidate.attraction_id)
            if prior is None or candidate.score > prior.score:
                best[candidate.attraction_id] = candidate
        return sorted(best.values(), key=lambda candidate: (-candidate.score, candidate.attraction_id))

    async def _hydrate(self, attraction_ids: list[int]) -> dict[int, HydratedAttraction]:
        if not attraction_ids or self.db is None:
            return {}
        result = await self.db.execute(
            select(Attraction).where(
                Attraction.id.in_(attraction_ids), Attraction.is_active.is_(True)
            )
        )
        attractions = {item.id: item for item in result.scalars().all()}
        category_rows = await self.db.execute(
            select(AttractionCategory.attraction_id, Category.name)
            .join(Category, Category.id == AttractionCategory.category_id)
            .where(
                AttractionCategory.attraction_id.in_(attraction_ids),
                Category.is_active.is_(True),
            )
        )
        activity_rows = await self.db.execute(
            select(AttractionActivity.attraction_id, Activity.name)
            .join(Activity, Activity.id == AttractionActivity.activity_id)
            .where(
                AttractionActivity.attraction_id.in_(attraction_ids),
                AttractionActivity.is_available.is_(True),
                Activity.is_active.is_(True),
            )
        )
        categories: dict[int, list[str]] = {}
        activities: dict[int, list[str]] = {}
        for attraction_id, name in category_rows.all():
            categories.setdefault(attraction_id, []).append(name)
        for attraction_id, name in activity_rows.all():
            activities.setdefault(attraction_id, []).append(name)
        district_rows = await self.db.execute(
            select(District.id, District.province).where(District.id.in_([
                attraction.district_id
                for attraction in attractions.values()
                if attraction.district_id is not None
            ]))
        )
        district_regions = {district_id: province for district_id, province in district_rows.all()}
        return {
            attraction_id: HydratedAttraction(
                attraction=attraction,
                category_names=tuple(sorted(set(categories.get(attraction_id, [])), key=_normalise)),
                activity_names=tuple(sorted(set(activities.get(attraction_id, [])), key=_normalise)),
                region_name=district_regions.get(attraction.district_id),
            )
            for attraction_id, attraction in attractions.items()
        }

    def rank_hydrated(
        self,
        request: ContentBasedRecommendationRequest,
        retrieval_query: str,
        candidates: list[SemanticCandidate],
        hydrated: dict[int, HydratedAttraction],
    ) -> ContentBasedRecommendationResponse:
        excluded: Counter[str] = Counter()
        items: list[ContentBasedRecommendationItem] = []
        for candidate in candidates:
            record = hydrated.get(candidate.attraction_id)
            if record is None:
                excluded["inactive_or_unavailable_postgresql_record"] += 1
                continue
            hard_filter_failure = self._hard_filter_failure(request, record)
            if hard_filter_failure:
                excluded[hard_filter_failure] += 1
                continue
            items.append(self._score_candidate(request, candidate, record))
        items.sort(key=lambda item: (-item.baseline_score, item.attraction_id))
        return ContentBasedRecommendationResponse(
            interests=request.interests,
            retrieval_query=retrieval_query,
            candidate_pool_requested=request.candidate_pool_size,
            candidates_retrieved=len(candidates),
            candidates_after_hard_filters=len(items),
            recommendations=items[: request.limit],
            excluded_candidate_counts=dict(sorted(excluded.items())),
        )

    @staticmethod
    def _hard_filter_failure(
        request: ContentBasedRecommendationRequest, record: HydratedAttraction
    ) -> str | None:
        filters = request.hard_filters
        category_names = _normalised_set(record.category_names)
        activity_names = _normalised_set(record.activity_names)
        wanted_categories = _normalised_set(filters.category_names)
        wanted_activities = _normalised_set(filters.activity_names)
        wanted_regions = _normalised_set(filters.region_names)
        attraction = record.attraction
        if filters.district_ids and attraction.district_id is None:
            return "hard_district_metadata_missing"
        if filters.district_ids and attraction.district_id not in set(filters.district_ids):
            return "hard_district_not_matched"
        if wanted_regions and record.region_name is None:
            return "hard_region_metadata_missing"
        if wanted_regions and _normalise(record.region_name) not in wanted_regions:
            return "hard_region_not_matched"
        if wanted_categories and not category_names:
            return "hard_category_metadata_missing"
        if wanted_categories and _preference_ratio(wanted_categories, category_names) < 1:
            return "hard_category_not_matched"
        if wanted_activities and not activity_names:
            return "hard_activity_metadata_missing"
        if wanted_activities and _preference_ratio(wanted_activities, activity_names) < 1:
            return "hard_activity_not_matched"
        if filters.max_price_level is not None and attraction.price_level is None:
            return "hard_budget_metadata_missing"
        if (
            filters.max_price_level is not None
            and attraction.price_level is not None
            and attraction.price_level > filters.max_price_level
        ):
            return "hard_budget_not_matched"
        return None

    @staticmethod
    def _score_candidate(
        request: ContentBasedRecommendationRequest,
        candidate: SemanticCandidate,
        record: HydratedAttraction,
    ) -> ContentBasedRecommendationItem:
        preferred_categories = _normalised_set(request.preferred_categories)
        preferred_activities = _normalised_set(request.preferred_activities)
        preferred_districts = set(request.preferred_district_ids)
        preferred_regions = _normalised_set(request.preferred_regions)
        categories = _normalised_set(record.category_names)
        activities = _normalised_set(record.activity_names)

        category_score = (
            None if not preferred_categories or not categories else _preference_ratio(preferred_categories, categories)
        )
        activity_score = (
            None if not preferred_activities or not activities else _preference_ratio(preferred_activities, activities)
        )
        district_score = (
            None
            if not preferred_districts or record.attraction.district_id is None
            else float(record.attraction.district_id in preferred_districts)
        )
        region_score = (
            None
            if not preferred_regions or record.region_name is None
            else float(_normalise(record.region_name) in preferred_regions)
        )
        semantic_score = _shift_cosine(candidate.score)
        weighted_components: list[tuple[float, float]] = [(request.weights.semantic, semantic_score)]
        if category_score is not None:
            weighted_components.append((request.weights.category, category_score))
        if activity_score is not None:
            weighted_components.append((request.weights.activity, activity_score))
        geographic_scores = [score for score in (district_score, region_score) if score is not None]
        if geographic_scores:
            # District and province are two evidence sources for one configured
            # geographic-preference component, never two hidden extra weights.
            weighted_components.append((request.weights.district, sum(geographic_scores) / len(geographic_scores)))
        weight_total = sum(weight for weight, _ in weighted_components)
        baseline_score = sum(weight * score for weight, score in weighted_components) / weight_total

        matched_categories = _matching_stored_names(preferred_categories, record.category_names)
        matched_activities = _matching_stored_names(preferred_activities, record.activity_names)
        evidence: dict[str, object] = {
            "category_names": list(record.category_names),
            "activity_names": list(record.activity_names),
            "matched_categories": matched_categories,
            "matched_activities": matched_activities,
            "district_preference_matched": district_score == 1.0 if district_score is not None else None,
            "region_name": record.region_name,
            "region_preference_matched": region_score == 1.0 if region_score is not None else None,
            "unavailable_dimensions": [
                name
                for name, score in (("category", category_score), ("activity", activity_score), ("district", district_score), ("region", region_score))
                if score is None
            ],
        }
        applied = []
        filters = request.hard_filters
        if filters.district_ids:
            applied.append("district_ids")
        if filters.region_names:
            applied.append("region_names")
        if filters.category_names:
            applied.append("category_names")
        if filters.activity_names:
            applied.append("activity_names")
        if filters.max_price_level is not None:
            applied.append("max_price_level")
        return ContentBasedRecommendationItem(
            attraction_id=record.attraction.id,
            attraction_name=record.attraction.name,
            district_id=record.attraction.district_id,
            baseline_score=round(baseline_score, 6),
            semantic_relevance_score=round(semantic_score, 6),
            raw_semantic_similarity=candidate.score,
            category_match_score=None if category_score is None else round(category_score, 6),
            activity_match_score=None if activity_score is None else round(activity_score, 6),
            district_match_score=None if district_score is None else round(district_score, 6),
            region_match_score=None if region_score is None else round(region_score, 6),
            applied_hard_filters=applied,
            matched_preference_evidence=evidence,
            ranking_explanation=(
                "Score is a re-normalized weighted average of shifted cosine similarity "
                "and only available requested category, activity, and district metadata. "
                "It is a baseline relevance score, not a calibrated probability."
            ),
        )
