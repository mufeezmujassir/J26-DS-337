from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.holiday_event.context_scoring import ContextScoreRequest, HolidayEventContextScoringService
from app.recommendation.unified_context.schemas import ContextEvidence, EvidenceStatus


_QUALITY = {"HIGH": 0.90, "MEDIUM": 0.65, "LOW": 0.40}


class HolidayEventAdapter:
    def __init__(self, db: AsyncSession):
        self.service = HolidayEventContextScoringService(db)

    async def score_batch(
        self, attraction_ids: list[int], travel_date, interests: list[str]
    ) -> dict[int, ContextEvidence]:
        if not attraction_ids:
            return {}
        response = await self.service.score(ContextScoreRequest(
            travel_date=travel_date, attraction_ids=attraction_ids, interests=interests
        ))
        evaluated_at = datetime.now(timezone.utc)
        output: dict[int, ContextEvidence] = {}
        for item in response.scores:
            available = item.context_suitability_score is not None
            output[item.attraction_id] = ContextEvidence(
                dimension="holiday_event",
                status=EvidenceStatus.AVAILABLE if available else EvidenceStatus.NOT_AVAILABLE,
                score=item.context_suitability_score,
                confidence=_QUALITY.get(item.context_confidence),
                confidence_label=item.context_confidence,
                source="verified_sri_lanka_holiday_and_event_repository",
                source_version=response.scoring_version,
                evaluated_at=evaluated_at,
                travel_date=travel_date,
                provenance={"evidence_sources": item.evidence_sources},
                explanation=item.explanation,
                limitations=item.uncertainty_flags,
                missing_data_indicators=item.missing_features,
                details=item.model_dump(mode="json"),
            )
        return output
