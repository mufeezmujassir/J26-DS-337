from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
from app.models.attraction import Attraction
from app.models.activities import Activity
from app.models.attraction_activities import AttractionActivity
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_descriptions import AttractionDescription
from app.models.categories import Category
from app.models.district import District
from app.recommendation.unified_context.adapters import (
    HolidayEventAdapter, SeasonalityAdapter, TimeOfDayAdapter, WeatherAdapter,
)
from app.recommendation.unified_context.reranker import ExperimentalContextReranker, RankingCandidate
from app.recommendation.unified_context.schemas import (
    CONTEXT_DIMENSIONS, ContextEvidence, EvidenceStatus, LatencyBreakdown,
    UnifiedContextRequest, UnifiedContextResponse,
)


class UnifiedContextEngineDisabled(RuntimeError):
    pass


def _normalize_semantic(score: float) -> float:
    return round(max(0.0, min(1.0, (score + 1.0) / 2.0)), 6)


def _preference_tokens(requested_activities: list[str], interests: list[str]) -> set[str]:
    """Expand user-facing preference labels into stored taxonomy fragments."""
    aliases = {
        "cultural sightseeing": {"cultur", "heritage", "history", "archaeolog"},
        "culture": {"cultur"},
        "heritage": {"heritage", "history", "archaeolog"},
        "religious": {"religio", "spiritual", "temple", "church", "mosque", "shrine", "buddh"},
    }
    tokens: set[str] = set()
    for value in [*requested_activities, *interests]:
        normalized = value.strip().casefold()
        if not normalized:
            continue
        tokens.update(aliases.get(normalized, {normalized}))
    return tokens


def _description_is_polluted(description: str) -> bool:
    """Detect imported guide-page fragments that describe unrelated places."""
    lowered = description.casefold()
    guide_markers = (
        "== sleep ==",
        "=== mid-range ===",
        "=== budget ===",
        "updated jan ",
        "updated feb ",
        "updated mar ",
        "updated apr ",
        "updated may ",
        "updated jun ",
        "updated jul ",
        "updated aug ",
        "updated sep ",
        "updated oct ",
        "updated nov ",
        "updated dec ",
    )
    return len(description) > 1800 or any(marker in lowered for marker in guide_markers)


def _metadata_description(attraction, district_name: str | None, category_names: list[str],
                          activity_names: list[str]) -> str:
    location = ", ".join(
        value for value in (attraction.city, district_name and f"{district_name} District") if value
    )
    kind = ", ".join(category_names[:3]) or "visitor attraction"
    sentences = [
        f"{attraction.name} is listed as a {kind.lower()} destination"
        f"{f' in {location}' if location else ''}."
    ]
    if activity_names:
        sentences.append(f"Available activities include {', '.join(activity_names[:5])}.")
    if attraction.rating is not None:
        review_text = f" from {attraction.review_count} reviews" if attraction.review_count else ""
        sentences.append(f"Its stored visitor rating is {attraction.rating:.1f}/5{review_text}.")
    return " ".join(sentences)


class UnifiedContextOrchestrator:
    def __init__(
        self,
        db: AsyncSession,
        retriever: SemanticAttractionRetriever | None = None,
        *,
        engine_enabled: bool | None = None,
        reranking_enabled: bool | None = None,
        timeout_seconds: float | None = None,
    ):
        self.db = db
        self.retriever = retriever or SemanticAttractionRetriever()
        self.engine_enabled = settings.ENABLE_UNIFIED_CONTEXT_ENGINE if engine_enabled is None else engine_enabled
        self.reranking_enabled = settings.ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING if reranking_enabled is None else reranking_enabled
        self.timeout_seconds = timeout_seconds or settings.UNIFIED_CONTEXT_ADAPTER_TIMEOUT_SECONDS

    async def recommend(self, request: UnifiedContextRequest) -> UnifiedContextResponse:
        if not self.engine_enabled or not self.reranking_enabled:
            raise UnifiedContextEngineDisabled("The unified context engine and experimental reranking flags must both be enabled.")
        if settings.ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING:
            raise UnifiedContextEngineDisabled("Production unified-context ranking is prohibited in Stage 12.5.")
        started = perf_counter()
        latency = LatencyBreakdown()
        errors: list[dict] = []

        t0 = perf_counter()
        if request.candidates:
            supplied = sorted(request.candidates, key=lambda item: (item.semantic_rank or 10**9, -item.semantic_score, item.attraction_id))
            raw = [(item.attraction_id, item.attraction_name, item.semantic_score, item.semantic_metadata) for item in supplied]
        else:
            try:
                retrieved = await asyncio.wait_for(
                    self.retriever.search(
                        self.db, request.query, limit=request.candidate_pool_size,
                        district_id=request.destination_district_id,
                    ),
                    timeout=settings.UNIFIED_CONTEXT_SEMANTIC_RETRIEVAL_TIMEOUT_SECONDS,
                )
                seen: set[int] = set()
                raw = []
                for item in retrieved:
                    if item.attraction_id not in seen:
                        seen.add(item.attraction_id)
                        raw.append((item.attraction_id, item.name, item.score, {
                            "source": "qdrant:sri_lanka_attractions", "city": item.city, "district_id": item.district_id,
                        }))
                if request.destination_district_id is not None:
                    raw = [item for item in raw if item[3].get("district_id") == request.destination_district_id]
            except (TimeoutError, RuntimeError) as exc:
                # Keep the local research UI usable while a cold embedding
                # model warms up or Qdrant is temporarily unavailable. The
                # fallback is explicitly recorded and never presented as
                # semantic evidence.
                errors.append({
                    "dimension": "semantic_retrieval",
                    "type": type(exc).__name__,
                    "message": "Semantic retrieval was unavailable; a deterministic database fallback was used.",
                })
                fallback = select(Attraction).where(Attraction.is_active.is_(True))
                if request.destination_district_id is not None:
                    fallback = fallback.where(
                        Attraction.district_id == request.destination_district_id
                    )
                preference_tokens = _preference_tokens(
                    request.requested_activities, request.interests
                )
                if preference_tokens:
                    category_match = exists(
                        select(1)
                        .select_from(AttractionCategory)
                        .join(Category, Category.id == AttractionCategory.category_id)
                        .where(
                            AttractionCategory.attraction_id == Attraction.id,
                            Category.is_active.is_(True),
                            or_(*[
                                func.lower(Category.name).contains(token)
                                for token in sorted(preference_tokens)
                            ]),
                        )
                    )
                    activity_match = exists(
                        select(1)
                        .select_from(AttractionActivity)
                        .join(Activity, Activity.id == AttractionActivity.activity_id)
                        .where(
                            AttractionActivity.attraction_id == Attraction.id,
                            AttractionActivity.is_available.is_(True),
                            Activity.is_active.is_(True),
                            or_(*[
                                func.lower(Activity.name).contains(token)
                                for token in sorted(preference_tokens)
                            ]),
                        )
                    )
                    fallback = fallback.where(or_(
                        category_match,
                        activity_match,
                        *[
                            func.lower(Attraction.name).contains(token)
                            for token in sorted(preference_tokens)
                        ],
                    ))
                fallback_rows = (await self.db.execute(
                    fallback.order_by(
                        Attraction.rating.desc().nulls_last(), Attraction.name
                    ).limit(request.candidate_pool_size)
                )).scalars().all()
                raw = [
                    (
                        item.id,
                        item.name,
                        0.0,
                        {
                            "source": "postgresql:deterministic_fallback",
                            "city": item.city,
                            "district_id": item.district_id,
                            "semantic_retrieval_available": False,
                        },
                    )
                    for item in fallback_rows
                ]
        latency.semantic_retrieval_ms = round((perf_counter() - t0) * 1000, 3)
        raw = raw[: settings.UNIFIED_CONTEXT_MAX_CANDIDATES]
        ids = [item[0] for item in raw]

        t0 = perf_counter()
        rows = (await self.db.execute(select(Attraction).where(
            Attraction.id.in_(ids), Attraction.is_active.is_(True)
        ))).scalars().all() if ids else []
        attraction_map = {item.id: item for item in rows}
        raw = [item for item in raw if item[0] in attraction_map]
        ids = [item[0] for item in raw]
        attractions = [attraction_map[item_id] for item_id in ids]

        district_rows = (await self.db.execute(
            select(District.id, District.name).where(District.id.in_({item.district_id for item in attractions if item.district_id}))
        )).all() if attractions else []
        district_names = dict(district_rows)

        description_rows = (await self.db.execute(
            select(
                AttractionDescription.attraction_id,
                AttractionDescription.description,
                AttractionDescription.source_url,
            ).where(
                AttractionDescription.attraction_id.in_(ids),
                AttractionDescription.is_active.is_(True),
                AttractionDescription.description.is_not(None),
            ).order_by(
                AttractionDescription.attraction_id,
                func.length(AttractionDescription.description).desc(),
            )
        )).all() if ids else []
        enriched_descriptions: dict[int, tuple[str, str | None]] = {}
        for attraction_id, description, source_url in description_rows:
            if attraction_id not in enriched_descriptions and description and description.strip():
                enriched_descriptions[attraction_id] = (description.strip(), source_url)

        category_rows = (await self.db.execute(
            select(AttractionCategory.attraction_id, Category.name)
            .join(Category, Category.id == AttractionCategory.category_id)
            .where(AttractionCategory.attraction_id.in_(ids), Category.is_active.is_(True))
            .order_by(AttractionCategory.attraction_id, AttractionCategory.is_primary.desc(), Category.name)
        )).all() if ids else []
        categories: dict[int, list[str]] = {}
        for attraction_id, name in category_rows:
            categories.setdefault(attraction_id, []).append(name)

        activity_rows = (await self.db.execute(
            select(AttractionActivity.attraction_id, Activity.name)
            .join(Activity, Activity.id == AttractionActivity.activity_id)
            .where(
                AttractionActivity.attraction_id.in_(ids),
                AttractionActivity.is_available.is_(True),
                Activity.is_active.is_(True),
            ).order_by(AttractionActivity.attraction_id, AttractionActivity.suitability_score.desc(), Activity.name)
        )).all() if ids else []
        activities: dict[int, list[str]] = {}
        for attraction_id, name in activity_rows:
            activities.setdefault(attraction_id, []).append(name)

        details_by_id: dict[int, dict] = {}
        for attraction in attractions:
            district_name = district_names.get(attraction.district_id)
            category_names = categories.get(attraction.id, [])
            activity_names = activities.get(attraction.id, [])
            description = attraction.description.strip() if attraction.description and attraction.description.strip() else None
            description_source = "attractions.description" if description else None
            if not description and attraction.id in enriched_descriptions:
                description, source_url = enriched_descriptions[attraction.id]
                description_source = source_url or "attraction_descriptions"
            if not description or _description_is_polluted(description):
                description = _metadata_description(
                    attraction, district_name, category_names, activity_names
                )
                description_source = "database_metadata_summary"
            details_by_id[attraction.id] = {
                "description": description,
                "description_source": description_source,
                "city": attraction.city,
                "district_name": district_name,
                "address": attraction.address,
                "latitude": attraction.latitude,
                "longitude": attraction.longitude,
                "rating": attraction.rating,
                "review_count": attraction.review_count,
                "phone_number": attraction.phone_number,
                "website_url": attraction.website_url,
                "opening_hours": attraction.opening_hours,
                "categories": category_names,
                "activities": activity_names,
            }
        latency.candidate_hydration_ms = round((perf_counter() - t0) * 1000, 3)

        # The adapters share one AsyncSession. SQLAlchemy sessions do not allow
        # concurrent operations, so database-backed batches are intentionally
        # controlled sequentially. Each layer is still timeout- and failure-isolated.
        evidence_by_dimension: dict[str, dict[int, ContextEvidence]] = {}
        activity = request.requested_activities[0] if request.requested_activities else None
        calls = [
            ("weather", WeatherAdapter(self.db).score_batch(attractions, request.travel_datetime.date(), activity)),
            ("time_of_day", TimeOfDayAdapter().score_batch(attractions, request.travel_datetime, request.visit_duration_minutes)),
            ("holiday_event", HolidayEventAdapter(self.db).score_batch(ids, request.travel_datetime.date(), request.interests)),
            ("historical_seasonality", SeasonalityAdapter(self.db).score_batch(ids, request.activity_type_id, request.travel_datetime.date())),
        ]
        for dimension, awaitable in calls:
            t0 = perf_counter()
            try:
                evidence_by_dimension[dimension] = await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
            except Exception as exc:
                errors.append({"dimension": dimension, "type": type(exc).__name__, "message": str(exc)})
                evidence_by_dimension[dimension] = {
                    attraction_id: self._error_evidence(dimension, request.travel_datetime.date(), exc)
                    for attraction_id in ids
                }
            setattr(latency, f"{dimension}_ms", round((perf_counter() - t0) * 1000, 3))

        ranking_input: list[RankingCandidate] = []
        explicit_terms = _preference_tokens(request.requested_activities, request.interests)
        for rank, (attraction_id, supplied_name, semantic_score, metadata) in enumerate(raw, 1):
            attraction = attraction_map[attraction_id]
            details = details_by_id.get(attraction_id, {})
            searchable_values = [
                attraction.name,
                *details.get("categories", []),
                *details.get("activities", []),
                *(
                    attraction.vibe_tags
                    if isinstance(attraction.vibe_tags, list)
                    else (attraction.vibe_tags or {}).values()
                    if isinstance(attraction.vibe_tags, dict)
                    else []
                ),
                *(
                    attraction.experience_tags
                    if isinstance(attraction.experience_tags, list)
                    else (attraction.experience_tags or {}).values()
                    if isinstance(attraction.experience_tags, dict)
                    else []
                ),
            ]
            searchable_text = " ".join(str(value).casefold() for value in searchable_values if value)
            explicit_preference_match = bool(explicit_terms) and any(
                term in searchable_text for term in explicit_terms
            )
            evidence = {
                dimension: evidence_by_dimension.get(dimension, {}).get(attraction_id)
                or self._missing_evidence(dimension, request.travel_datetime.date())
                for dimension in CONTEXT_DIMENSIONS
            }
            ranking_input.append(RankingCandidate(
                attraction_id=attraction_id,
                attraction_name=attraction.name or supplied_name or str(attraction_id),
                semantic_score=semantic_score,
                normalized_semantic_score=_normalize_semantic(semantic_score),
                semantic_rank=rank,
                evidence=evidence,
                semantic_metadata=metadata,
                details=details,
                explicit_preference_match=explicit_preference_match,
            ))
        t0 = perf_counter()
        ranked = ExperimentalContextReranker().rerank(ranking_input, request.configuration, request.semantic_alpha)
        if explicit_terms:
            # Do not pad a specific request (for example, "beach") with
            # unrelated district records merely to reach the numeric limit.
            # Returning fewer, verified matches is preferable to a longer but
            # misleading list.
            matched = [item for item in ranked if item.explicit_preference_match]
            ranked = [
                item.model_copy(update={"experimental_rank": rank})
                for rank, item in enumerate(matched, 1)
            ]
        latency.reranking_ms = round((perf_counter() - t0) * 1000, 3)
        latency.end_to_end_ms = round((perf_counter() - started) * 1000, 3)
        original = ids
        return UnifiedContextResponse(
            query=request.query,
            travel_datetime=request.travel_datetime,
            configuration=request.configuration,
            candidates=ranked[:request.limit],
            original_candidate_order=original,
            experimental_candidate_order=[item.attraction_id for item in ranked],
            production_candidate_order=original,
            errors=errors,
            latency=latency,
        )

    @staticmethod
    def _error_evidence(dimension: str, travel_date, exc: Exception) -> ContextEvidence:
        return ContextEvidence(
            dimension=dimension, status=EvidenceStatus.ERROR,
            evaluated_at=datetime.now(timezone.utc), travel_date=travel_date,
            explanation=f"The {dimension} adapter failed in isolation; other context layers continued.",
            limitations=[f"{type(exc).__name__}: {exc}"],
            missing_data_indicators=["adapter_result"],
        )

    @staticmethod
    def _missing_evidence(dimension: str, travel_date) -> ContextEvidence:
        return ContextEvidence(
            dimension=dimension, status=EvidenceStatus.NOT_AVAILABLE,
            evaluated_at=datetime.now(timezone.utc), travel_date=travel_date,
            explanation=f"No {dimension} evidence was returned for this candidate.",
            missing_data_indicators=["candidate_evidence"],
        )
