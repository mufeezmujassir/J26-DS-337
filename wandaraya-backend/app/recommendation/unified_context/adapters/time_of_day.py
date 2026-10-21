from __future__ import annotations

from datetime import datetime, timezone

from app.models.attraction import Attraction
from app.recommendation.time_context.service import evaluate_attraction_time_evidence
from app.recommendation.unified_context.schemas import ContextEvidence, EvidenceStatus


class TimeOfDayAdapter:
    source_version = "stage12_2_existing_schedule_policy"

    async def score_batch(
        self,
        attractions: list[Attraction],
        travel_datetime: datetime,
        visit_duration_minutes: int,
    ) -> dict[int, ContextEvidence]:
        evaluated_at = datetime.now(timezone.utc)
        output: dict[int, ContextEvidence] = {}
        for attraction in attractions:
            item = evaluate_attraction_time_evidence(attraction, travel_datetime, visit_duration_minutes)
            available = item["score"] is not None
            output[attraction.id] = ContextEvidence(
                dimension="time_of_day",
                status=EvidenceStatus.AVAILABLE if available else EvidenceStatus.NOT_AVAILABLE,
                score=item["score"],
                confidence=0.60 if available else None,
                confidence_label=item["confidence"],
                source=item["source"],
                source_version=self.source_version,
                evaluated_at=evaluated_at,
                travel_date=travel_datetime.date(),
                provenance={"timezone": "Asia/Colombo", "freshness": item["freshness"]},
                explanation=item["explanation"],
                limitations=([] if available else ["Opening hours or visit-window evidence is unavailable."]),
                missing_data_indicators=item["unavailable_dimensions"],
                details={
                    "opening_status": item["opening_status"],
                    "visit_window_status": item["visit_window_status"],
                    "visit_duration_minutes": visit_duration_minutes,
                },
            )
        return output
