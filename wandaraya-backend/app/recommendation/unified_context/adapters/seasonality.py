from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.climate.services.seasonality_scoring import (
    ExperimentalSeasonalityScoringService,
    SeasonalityScoreRequest,
)
from app.recommendation.unified_context.schemas import ContextEvidence, EvidenceStatus


_TIER_QUALITY = {"A": 0.90, "B": 0.75, "C": 0.50, "D": 0.30}


class SeasonalityAdapter:
    def __init__(self, db: AsyncSession):
        self.service = ExperimentalSeasonalityScoringService(db)
        self.query_count = 0

    async def score_batch(
        self, attraction_ids: list[int], activity_type_id: int | None, travel_date
    ) -> dict[int, ContextEvidence]:
        evaluated_at = datetime.now(timezone.utc)
        if activity_type_id is None:
            return {
                attraction_id: ContextEvidence(
                    dimension="historical_seasonality",
                    status=EvidenceStatus.NOT_AVAILABLE,
                    evaluated_at=evaluated_at,
                    travel_date=travel_date,
                    source="stage12_4f_conservative_policy",
                    source_version="stage12_4f_conservative_v1",
                    explanation="No activity type ID was supplied, so the persisted attraction-activity seasonality mapping cannot be queried.",
                    limitations=["Historical climate evidence is activity-specific."],
                    missing_data_indicators=["activity_type_id"],
                ) for attraction_id in attraction_ids
            }
        results = await self.service.score_batch([
            SeasonalityScoreRequest(
                attraction_id=attraction_id,
                activity_type_id=activity_type_id,
                travel_date=travel_date,
            ) for attraction_id in attraction_ids
        ])
        self.query_count = self.service.last_query_count
        output: dict[int, ContextEvidence] = {}
        for item in results:
            available = item.availability_status == "AVAILABLE" and item.seasonality_suitability_score is not None
            output[item.attraction_id] = ContextEvidence(
                dimension="historical_seasonality",
                status=EvidenceStatus.AVAILABLE if available else EvidenceStatus.NOT_AVAILABLE,
                score=item.seasonality_suitability_score,
                confidence=_TIER_QUALITY.get(item.activity_mapping_confidence),
                confidence_label=item.activity_mapping_confidence,
                source="persisted_historical_climate_seasonality",
                source_version=item.model_version,
                evaluated_at=evaluated_at,
                travel_date=travel_date,
                provenance=item.climate_feature_provenance,
                explanation=(item.explanation_metadata.get("summary") or item.fallback_reason or
                             "Historical seasonality evidence is available." if available else
                             "Historical seasonality evidence is unavailable."),
                limitations=item.evidence_limitations,
                missing_data_indicators=item.missing_data_indicators,
                fallback_used=item.fallback_used,
                fallback_reason=item.fallback_reason,
                details=item.model_dump(mode="json"),
            )
        return output
