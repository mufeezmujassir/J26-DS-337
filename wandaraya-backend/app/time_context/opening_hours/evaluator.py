"""Pure weekly-schedule evaluation with explicit uncertainty."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.time_context.opening_hours.schemas import (
    GoogleWeekday,
    IntervalType,
    NormalizedWeeklySchedule,
    OpeningHoursEvaluation,
    OpeningReasonCode,
    OpeningState,
    ScheduleValidationStatus,
)


_MINUTES_PER_DAY = 24 * 60
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY


def evaluate_weekly_schedule(
    schedule: NormalizedWeeklySchedule,
    visit_at: datetime,
) -> OpeningHoursEvaluation:
    """Evaluate only regular weekly hours; exceptions are intentionally unknown."""
    if visit_at.tzinfo is None or visit_at.utcoffset() is None:
        raise ValueError("visit_at must be timezone-aware")
    local_visit = visit_at.astimezone(ZoneInfo(schedule.timezone))
    if schedule.validation_status is not ScheduleValidationStatus.VALID:
        reason = {
            ScheduleValidationStatus.MISSING: OpeningReasonCode.SCHEDULE_MISSING,
            ScheduleValidationStatus.MALFORMED: OpeningReasonCode.SCHEDULE_MALFORMED,
            ScheduleValidationStatus.AMBIGUOUS: OpeningReasonCode.SCHEDULE_AMBIGUOUS,
            ScheduleValidationStatus.UNSUPPORTED: OpeningReasonCode.SCHEDULE_UNSUPPORTED,
            ScheduleValidationStatus.CONFLICTING: OpeningReasonCode.SCHEDULE_CONFLICTING,
        }[schedule.validation_status]
        return OpeningHoursEvaluation(
            attraction_id=schedule.attraction_id,
            evaluated_local_datetime=local_visit,
            weekly_schedule_status=schedule.validation_status,
            state=OpeningState.UNKNOWN,
            evidence_completeness="insufficient",
            reason_codes=[reason],
            evidence=schedule.evidence,
            explanation="No trustworthy weekly opening-hours determination can be made from this schedule.",
        )
    if any(item.interval_type is IntervalType.ALWAYS_OPEN for item in schedule.intervals):
        state, reason = OpeningState.KNOWN_OPEN, OpeningReasonCode.WITHIN_OPENING_INTERVAL
    else:
        minute = _local_minute_of_week(local_visit)
        state = (
            OpeningState.KNOWN_OPEN
            if any(_contains(interval, minute) for interval in schedule.intervals)
            else OpeningState.KNOWN_CLOSED
        )
        reason = (
            OpeningReasonCode.WITHIN_OPENING_INTERVAL
            if state is OpeningState.KNOWN_OPEN
            else OpeningReasonCode.OUTSIDE_OPENING_INTERVAL
        )
    return OpeningHoursEvaluation(
        attraction_id=schedule.attraction_id,
        evaluated_local_datetime=local_visit,
        weekly_schedule_status=schedule.validation_status,
        state=state,
        evidence_completeness="regular_weekly_hours_only",
        reason_codes=[
            OpeningReasonCode.SCHEDULE_VALID_REGULAR_WEEKLY_ONLY,
            reason,
            OpeningReasonCode.DATE_EXCEPTIONS_NOT_CHECKED,
        ],
        evidence=schedule.evidence,
        explanation=(
            "The visit time is within the stored regular weekly opening interval. "
            if state is OpeningState.KNOWN_OPEN
            else "The visit time is outside the stored regular weekly opening intervals. "
        ) + "Date-specific exceptions, temporary closures and last-entry rules were not checked.",
    )


def _local_minute_of_week(value: datetime) -> int:
    # datetime.weekday() uses Monday=0. Google uses Sunday=0.
    google_day = GoogleWeekday((value.weekday() + 1) % 7)
    return int(google_day) * _MINUTES_PER_DAY + value.hour * 60 + value.minute


def _contains(interval, minute: int) -> bool:
    start = int(interval.start_weekday) * _MINUTES_PER_DAY + _to_minutes(interval.start_local_time)
    assert interval.end_weekday is not None and interval.end_local_time is not None
    end = int(interval.end_weekday) * _MINUTES_PER_DAY + _to_minutes(interval.end_local_time)
    if interval.overnight and end <= start:
        end += _MINUTES_PER_WEEK
    if end <= _MINUTES_PER_WEEK:
        return start <= minute < end
    return minute >= start or minute < end - _MINUTES_PER_WEEK


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute
