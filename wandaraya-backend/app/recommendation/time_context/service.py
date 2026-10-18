"""Time-of-day adapter built strictly on stored verified weekly schedules."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.recommendation.time_context.advisory import load_advisory_for_attraction
from app.recommendation.content_based.service import ContentBasedRecommendationService
from app.recommendation.time_context.schemas import TimeAwareRecommendationRequest, TimeAwareResponse, TimeContextEvidenceItem
from app.time_context.opening_hours.evaluator import evaluate_weekly_schedule
from app.time_context.opening_hours.google_period_parser import normalize_google_regular_opening_hours
from app.time_context.opening_hours.schemas import OpeningState, IntervalType


def _remaining_minutes(schedule, local_visit: datetime) -> int | None:
    """Return remaining minutes in the verified open interval, or None."""
    if any(interval.interval_type is IntervalType.ALWAYS_OPEN for interval in schedule.intervals):
        return 24 * 60
    # Reuse evaluator's inclusive-open/exclusive-close semantics. This compact
    # calculation is only used after it has confirmed OPEN.
    weekday = (local_visit.weekday() + 1) % 7
    minute = weekday * 1440 + local_visit.hour * 60 + local_visit.minute
    candidates: list[int] = []
    for item in schedule.intervals:
        start = int(item.start_weekday) * 1440 + item.start_local_time.hour * 60 + item.start_local_time.minute
        end = int(item.end_weekday) * 1440 + item.end_local_time.hour * 60 + item.end_local_time.minute
        if item.overnight and end <= start:
            end += 7 * 1440
        current = minute if minute >= start else minute + 7 * 1440
        if start <= current < end:
            candidates.append(end - current)
    return min(candidates) if candidates else None


class TimeAwareRecommendationService:
    def __init__(self, db: AsyncSession, content_service: ContentBasedRecommendationService | None = None):
        self.db = db
        self.content_service = content_service or ContentBasedRecommendationService(db)

    async def recommend(self, request: TimeAwareRecommendationRequest) -> TimeAwareResponse:
        baseline = await self.content_service.recommend(request)
        ids = [item.attraction_id for item in baseline.recommendations]
        rows = await self.db.execute(select(Attraction).where(Attraction.id.in_(ids), Attraction.is_active.is_(True)))
        attractions = {item.id: item for item in rows.scalars().all()}
        local_visit = request.visit_datetime.astimezone(ZoneInfo("Asia/Colombo"))
        result: list[TimeContextEvidenceItem] = []
        for baseline_item in baseline.recommendations:
            attraction = attractions.get(baseline_item.attraction_id)
            if attraction is None:
                continue
            schedule = normalize_google_regular_opening_hours(attraction_id=attraction.id, opening_hours=attraction.opening_hours)
            evaluation = evaluate_weekly_schedule(schedule, local_visit)
            if evaluation.state is OpeningState.UNKNOWN:
                opening, window, score, confidence = "UNKNOWN", "UNKNOWN", None, "unavailable"
                unavailable = ["verified_opening_hours"]
            elif evaluation.state is OpeningState.KNOWN_CLOSED:
                opening, window, score, confidence, unavailable = "CLOSED", "UNKNOWN", 0.0, "medium", []
            else:
                remaining = _remaining_minutes(schedule, local_visit)
                if remaining is None:
                    opening, window, score, confidence, unavailable = "UNKNOWN", "UNKNOWN", None, "unavailable", ["visit_window"]
                elif remaining >= request.visit_duration_minutes:
                    opening, window, score, confidence, unavailable = "OPEN", "FITS", 1.0, "medium", []
                else:
                    opening, window, score, confidence, unavailable = "OPEN", "INSUFFICIENT_TIME", 0.5, "medium", []
            if request.strict_open_now and opening != "OPEN":
                continue
            # Unknown schedule is intentionally not a zero score and therefore
            # preserves baseline ordering. Known time evidence is blended.
            final_score = baseline_item.baseline_score if score is None else ((1 - request.time_weight) * baseline_item.baseline_score + request.time_weight * score)
            result.append(TimeContextEvidenceItem(
                **baseline_item.model_dump(), opening_status=opening, visit_window_status=window,
                time_suitability_score=score, time_context_confidence=confidence,
                time_evidence_source=schedule.source_type,
                time_evidence_freshness=schedule.evidence.freshness_status.value,
                time_explanation=evaluation.explanation,
                time_unavailable_dimensions=unavailable,
                final_experimental_score=round(final_score, 6),
                best_time_advisory=(load_advisory_for_attraction(attraction.id) if request.include_best_time_advisory else None),
            ))
        result.sort(key=lambda item: (-item.final_experimental_score, item.attraction_id))
        return TimeAwareResponse(
            visit_datetime_local=local_visit, visit_duration_minutes=request.visit_duration_minutes,
            strict_open_now=request.strict_open_now, candidates_from_content_baseline=len(baseline.recommendations),
            candidates_after_time_constraint=len(result), recommendations=result,
        )
