"""Strict, deterministic parser for stored Google ``regularOpeningHours``.

The parser reads only the normalised JSON stored by AttractionNormalizer.  It
does not mutate that object and deliberately does not use ``open_now`` because
it is a retrieval-time observation, not evidence for a future visit.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import time
from typing import Any

from app.time_context.opening_hours.schemas import (
    GoogleWeekday,
    IntervalType,
    NormalizedOpeningInterval,
    NormalizedWeeklySchedule,
    ScheduleValidationStatus,
)
from app.time_context.schemas import (
    FreshnessStatus,
    TimingEvidence,
    TimingSourceType,
    VerificationStatus,
)


GOOGLE_WEEKLY_PARSER_VERSION = "google-weekly-v1"
_MINUTES_PER_DAY = 24 * 60
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY


def normalize_google_regular_opening_hours(
    *,
    attraction_id: int,
    opening_hours: Any,
    timezone: str = "Asia/Colombo",
    evidence: TimingEvidence | None = None,
) -> NormalizedWeeklySchedule:
    """Normalise a stored Google weekly schedule without trusting missing data."""
    source_evidence = evidence or TimingEvidence(
        source_type=TimingSourceType.GOOGLE_PLACES,
        verification_status=VerificationStatus.SOURCE_REPORTED,
        freshness_status=FreshnessStatus.NOT_ASSESSED,
        limitations=[
            "Opening-hours provenance and retrieval timestamp are not independently stored.",
            "Regular weekly hours do not include date-specific exceptions in this evaluation.",
        ],
    )
    common = {
        "attraction_id": attraction_id,
        "timezone": timezone,
        "source_type": source_evidence.source_type.value,
        "parser_version": GOOGLE_WEEKLY_PARSER_VERSION,
        "evidence": source_evidence,
    }
    if opening_hours is None:
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.MISSING,
            warnings=["opening_hours is absent or JSON null."],
        )
    if not isinstance(opening_hours, dict):
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.MALFORMED,
            warnings=["opening_hours must be an object."],
        )
    # Do not modify input, including nested ``periods`` values.
    if "periods" not in opening_hours:
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.AMBIGUOUS,
            warnings=["periods is absent; no opening or closure can be inferred."],
        )
    periods = deepcopy(opening_hours.get("periods"))
    warnings: list[str] = []
    if "open_now" in opening_hours:
        warnings.append("open_now was ignored because it is not future-date schedule evidence.")
    if not isinstance(periods, list):
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.MALFORMED,
            warnings=warnings + ["periods must be an array."],
        )
    if not periods:
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.AMBIGUOUS,
            warnings=warnings + ["An empty periods array does not establish that the attraction is closed."],
        )

    intervals: list[NormalizedOpeningInterval] = []
    for index, period in enumerate(periods):
        parsed, error = _parse_period(period, index)
        if error is not None:
            if error.startswith("ambiguous"):
                status = ScheduleValidationStatus.AMBIGUOUS
            elif "unsupported" in error:
                status = ScheduleValidationStatus.UNSUPPORTED
            else:
                status = ScheduleValidationStatus.MALFORMED
            return NormalizedWeeklySchedule(
                **common,
                validation_status=status,
                warnings=warnings + [error],
            )
        intervals.append(parsed)

    conflict = _find_conflict(intervals)
    if conflict is not None:
        return NormalizedWeeklySchedule(
            **common,
            validation_status=ScheduleValidationStatus.CONFLICTING,
            warnings=warnings + [conflict],
        )
    return NormalizedWeeklySchedule(
        **common,
        intervals=intervals,
        validation_status=ScheduleValidationStatus.VALID,
        warnings=warnings,
    )


def _parse_period(period: Any, index: int) -> tuple[NormalizedOpeningInterval | None, str | None]:
    if not isinstance(period, dict):
        return None, f"period[{index}] must be an object."
    start, error = _google_point(period.get("open"), f"period[{index}].open")
    if error is not None:
        return None, error
    assert start is not None
    close = period.get("close")
    if close is None:
        # Google documents only Sunday 00:00 without a close as its unambiguous
        # all-week 24-hour representation. Other missing closes remain unknown.
        if start == (GoogleWeekday.SUNDAY, time(0, 0)) and len(period) == 1:
            return NormalizedOpeningInterval(
                start_weekday=start[0], start_local_time=start[1],
                interval_type=IntervalType.ALWAYS_OPEN,
            ), None
        return None, f"ambiguous period[{index}] has no close; it is not the documented 24-hour representation."
    end, error = _google_point(close, f"period[{index}].close")
    if error is not None:
        return None, error
    assert end is not None
    start_day, start_time = start
    end_day, end_time = end
    day_delta = (int(end_day) - int(start_day)) % 7
    if day_delta == 0:
        if end_time <= start_time:
            return None, f"period[{index}] closes at or before its same-day opening time."
        return NormalizedOpeningInterval(
            start_weekday=start_day, start_local_time=start_time,
            end_weekday=end_day, end_local_time=end_time,
            overnight=False, interval_type=IntervalType.REGULAR,
        ), None
    if day_delta != 1:
        return None, f"period[{index}] spans more than one day and is unsupported by this weekly parser."
    return NormalizedOpeningInterval(
        start_weekday=start_day, start_local_time=start_time,
        end_weekday=end_day, end_local_time=end_time,
        overnight=True, interval_type=IntervalType.OVERNIGHT,
    ), None


def _google_point(value: Any, label: str) -> tuple[tuple[GoogleWeekday, time] | None, str | None]:
    if not isinstance(value, dict):
        return None, f"{label} must be an object."
    day, hour, minute = value.get("day"), value.get("hour"), value.get("minute")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in (day, hour, minute)):
        return None, f"{label} day, hour and minute must be integers."
    if not 0 <= day <= 6:
        return None, f"{label}.day must be in Google range 0..6 (Sunday..Saturday)."
    if not 0 <= hour <= 23:
        return None, f"{label}.hour must be in range 0..23."
    if not 0 <= minute <= 59:
        return None, f"{label}.minute must be in range 0..59."
    return (GoogleWeekday(day), time(hour, minute)), None


def _find_conflict(intervals: list[NormalizedOpeningInterval]) -> str | None:
    if any(item.interval_type is IntervalType.ALWAYS_OPEN for item in intervals):
        if len(intervals) > 1:
            return "The documented always-open representation cannot be combined with other periods."
        return None
    segments: list[tuple[int, int]] = []
    for interval in intervals:
        start = int(interval.start_weekday) * _MINUTES_PER_DAY + _to_minutes(interval.start_local_time)
        assert interval.end_weekday is not None and interval.end_local_time is not None
        end = int(interval.end_weekday) * _MINUTES_PER_DAY + _to_minutes(interval.end_local_time)
        if interval.overnight and end <= start:
            end += _MINUTES_PER_WEEK
        if end <= _MINUTES_PER_WEEK:
            segments.append((start, end))
        else:
            segments.extend(((start, _MINUTES_PER_WEEK), (0, end - _MINUTES_PER_WEEK)))
    segments.sort()
    for previous, current in zip(segments, segments[1:]):
        if current[0] < previous[1]:
            return "Opening periods overlap or contradict each other."
    return None


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute
