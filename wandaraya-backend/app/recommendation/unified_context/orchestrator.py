from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
from app.models.attraction import Attraction
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
            retrieved = await self.retriever.search(self.db, request.query, limit=request.candidate_pool_size)
            seen: set[int] = set()
            raw = []
            for item in retrieved:
                if item.attraction_id not in seen:
                    seen.add(item.attraction_id)
                    raw.append((item.attraction_id, item.name, item.score, {
                        "source": "qdrant:sri_lanka_attractions", "city": item.city, "district_id": item.district_id,
                    }))
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
        for rank, (attraction_id, supplied_name, semantic_score, metadata) in enumerate(raw, 1):
            attraction = attraction_map[attraction_id]
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
            ))
        t0 = perf_counter()
        ranked = ExperimentalContextReranker().rerank(ranking_input, request.configuration, request.semantic_alpha)
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
