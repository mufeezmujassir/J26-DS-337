"""Additive shadow composition; evidence is never converted into ranking weights."""
from __future__ import annotations

from datetime import datetime
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.climate.services.seasonality_scoring import ExperimentalSeasonalityScoringService, SeasonalityScoreRequest
from app.config import settings
from app.holiday_event.context_scoring import ContextScoreRequest, HolidayEventContextScoringService
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
from app.models.attraction import Attraction
from app.recommendation.time_context.service import evaluate_attraction_time_evidence
from .schemas import ContextDimensionEvidence, ExperimentalCandidateEvidenceBundle, ExperimentalContextCompositionResponse


class ExperimentalCompositionDisabled(RuntimeError):
    """The internal shadow composition flag is disabled."""


class ExperimentalContextCompositionService:
    def __init__(self, db: AsyncSession, retriever: SemanticAttractionRetriever | None = None, *,
                 composition_enabled: bool | None = None, seasonality_enabled: bool | None = None):
        self.db = db
        self.retriever = retriever or SemanticAttractionRetriever()
        self.composition_enabled = settings.ENABLE_EXPERIMENTAL_CONTEXT_COMPOSITION if composition_enabled is None else composition_enabled
        self.seasonality_enabled = settings.ENABLE_EXPERIMENTAL_SEASONALITY_EVIDENCE if seasonality_enabled is None else seasonality_enabled

    async def compose(self, *, query: str, travel_datetime: datetime, activity_type_id: int,
                      limit: int = 10, interests: list[str] | None = None,
                      visit_duration_minutes: int = 60) -> ExperimentalContextCompositionResponse:
        if not self.composition_enabled:
            raise ExperimentalCompositionDisabled("ENABLE_EXPERIMENTAL_CONTEXT_COMPOSITION is false")
        if settings.ENABLE_SEASONALITY_PRODUCTION_RERANKING:
            raise ExperimentalCompositionDisabled("production seasonality reranking must remain disabled during Stage 12.4G")
        started = perf_counter()
        retrieved = await self.retriever.search(self.db, query, limit=limit)
        seen, candidates = set(), []
        for item in retrieved:
            if item.attraction_id not in seen:
                seen.add(item.attraction_id)
                candidates.append(item)
        ids = [c.attraction_id for c in candidates]
        rows = (await self.db.execute(select(Attraction).where(Attraction.id.in_(ids), Attraction.is_active.is_(True)))).scalars().all() if ids else []
        attractions = {a.id: a for a in rows}
        errors = []
        holiday = {}
        if ids:
            try:
                response = await HolidayEventContextScoringService(self.db).score(ContextScoreRequest(
                    travel_date=travel_datetime.date(), attraction_ids=ids, interests=interests or []))
                holiday = {x.attraction_id: x for x in response.scores}
            except Exception as exc:  # a shadow dimension must not break retrieval
                errors.append(f"holiday_event:{type(exc).__name__}:{exc}")
        seasonality, seasonality_ms, batch_queries = {}, 0.0, 0
        if self.seasonality_enabled and ids:
            service = ExperimentalSeasonalityScoringService(self.db)
            s0 = perf_counter()
            results = await service.score_batch([SeasonalityScoreRequest(
                attraction_id=i, activity_type_id=activity_type_id, travel_date=travel_datetime.date()) for i in ids])
            seasonality_ms = (perf_counter() - s0) * 1000
            batch_queries = service.last_query_count
            seasonality = {x.attraction_id: x for x in results}
        bundles = []
        for rank, candidate in enumerate(candidates, 1):
            attraction = attractions.get(candidate.attraction_id)
            time_item = evaluate_attraction_time_evidence(attraction, travel_datetime, visit_duration_minutes) if attraction else None
            holiday_item = holiday.get(candidate.attraction_id)
            season_item = seasonality.get(candidate.attraction_id)
            bundles.append(ExperimentalCandidateEvidenceBundle(
                attraction_id=candidate.attraction_id, attraction_name=candidate.name,
                original_semantic_rank=rank, semantic_score=candidate.score,
                semantic=ContextDimensionEvidence(status="AVAILABLE", score=candidate.score,
                    provenance={"source": "qdrant:sri_lanka_attractions", "rank": rank}),
                time_of_day=(ContextDimensionEvidence(status="AVAILABLE" if time_item and time_item["score"] is not None else "UNAVAILABLE",
                    score=time_item["score"] if time_item else None,
                    provenance={"source": time_item["source"]} if time_item else {},
                    limitations=time_item["unavailable_dimensions"] if time_item else ["attraction_metadata"],
                    details=time_item or {})),
                holiday_event=(ContextDimensionEvidence(status="AVAILABLE" if holiday_item and holiday_item.context_suitability_score is not None else "UNAVAILABLE",
                    score=holiday_item.context_suitability_score if holiday_item else None,
                    provenance={"scoring_version": "stage12_3d_context_v1", "sources": holiday_item.evidence_sources} if holiday_item else {},
                    limitations=holiday_item.missing_features if holiday_item else ["holiday_event_service_error_or_no_evidence"],
                    details=holiday_item.model_dump() if holiday_item else {})),
                historical_seasonality=(ContextDimensionEvidence(
                    status=("AVAILABLE" if season_item and season_item.availability_status == "AVAILABLE" else "UNAVAILABLE") if self.seasonality_enabled else "DISABLED",
                    score=season_item.seasonality_suitability_score if season_item else None,
                    provenance=season_item.climate_feature_provenance if season_item else {},
                    limitations=season_item.evidence_limitations if season_item else ([] if not self.seasonality_enabled else ["seasonality_evidence_unavailable"]),
                    details=season_item.model_dump(mode="json") if season_item else {})),
                group_emotion=ContextDimensionEvidence(status="NOT_AVAILABLE", score=None,
                    limitations=["No compatible Group Emotion context service exists in the repository."]),
            ))
        original = ids
        returned = [x.attraction_id for x in bundles]
        return ExperimentalContextCompositionResponse(query=query, travel_datetime=travel_datetime,
            activity_type_id=activity_type_id, candidates=bundles,
            original_candidate_order=original, returned_candidate_order=returned,
            ranking_unchanged=original == returned, production_ranking_changed=False,
            production_reranking_enabled=False, service_latency_ms=(perf_counter()-started)*1000,
            seasonality_latency_ms=seasonality_ms, seasonality_batch_query_count=batch_queries,
            errors=errors, flags={"experimental_context_composition": self.composition_enabled,
                "experimental_seasonality_evidence": self.seasonality_enabled,
                "seasonality_production_reranking": False})
