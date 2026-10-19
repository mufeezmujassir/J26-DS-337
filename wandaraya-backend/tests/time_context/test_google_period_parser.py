from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.time_context.opening_hours.evaluator import evaluate_weekly_schedule
from app.time_context.opening_hours.google_period_parser import (
    normalize_google_regular_opening_hours,
)
from app.time_context.opening_hours.schemas import (
    GoogleWeekday,
    OpeningReasonCode,
    OpeningState,
    ScheduleValidationStatus,
)
from app.time_context.schemas import (
    FreshnessStatus,
    TimeContextRequest,
    TimingEvidence,
    TimingSourceType,
    VerificationStatus,
)


def point(day, hour, minute=0):
    return {"day": day, "hour": hour, "minute": minute}


def schedule(periods, **extra):
    return {"open_now": extra.pop("open_now", True), "periods": periods, **extra}


def normalize(periods, **extra):
    return normalize_google_regular_opening_hours(
        attraction_id=1, opening_hours=schedule(periods, **extra)
    )


def evaluate(parsed, value):
    return evaluate_weekly_schedule(parsed, value.replace(tzinfo=ZoneInfo("Asia/Colombo")))


def test_sunday_google_day_zero_is_not_monday():
    parsed = normalize([{"open": point(0, 9), "close": point(0, 17)}])
    assert parsed.intervals[0].start_weekday is GoogleWeekday.SUNDAY
    assert evaluate(parsed, datetime(2026, 10, 18, 10)).state is OpeningState.KNOWN_OPEN  # Sunday
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.KNOWN_CLOSED  # Monday


def test_monday_google_day_one_is_open_on_monday():
    parsed = normalize([{"open": point(1, 9), "close": point(1, 17)}])
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.KNOWN_OPEN


def test_multiple_and_split_same_day_intervals():
    parsed = normalize([
        {"open": point(1, 9), "close": point(1, 12)},
        {"open": point(1, 13), "close": point(1, 17)},
    ])
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.KNOWN_OPEN
    assert evaluate(parsed, datetime(2026, 10, 19, 12, 30)).state is OpeningState.KNOWN_CLOSED
    assert evaluate(parsed, datetime(2026, 10, 19, 16, 59)).state is OpeningState.KNOWN_OPEN


def test_opening_boundary_inclusive_and_closing_boundary_exclusive():
    parsed = normalize([{"open": point(1, 9), "close": point(1, 17)}])
    assert evaluate(parsed, datetime(2026, 10, 19, 9)).state is OpeningState.KNOWN_OPEN
    assert evaluate(parsed, datetime(2026, 10, 19, 17)).state is OpeningState.KNOWN_CLOSED


def test_overnight_period_and_midnight_boundary():
    parsed = normalize([{"open": point(1, 22), "close": point(2, 2)}])
    assert parsed.intervals[0].overnight is True
    assert evaluate(parsed, datetime(2026, 10, 19, 23, 59)).state is OpeningState.KNOWN_OPEN
    assert evaluate(parsed, datetime(2026, 10, 20, 0)).state is OpeningState.KNOWN_OPEN
    assert evaluate(parsed, datetime(2026, 10, 20, 2)).state is OpeningState.KNOWN_CLOSED


def test_saturday_to_sunday_and_sunday_to_monday_week_boundaries():
    saturday = normalize([{"open": point(6, 22), "close": point(0, 2)}])
    sunday = normalize([{"open": point(0, 22), "close": point(1, 2)}])
    assert evaluate(saturday, datetime(2026, 10, 18, 1)).state is OpeningState.KNOWN_OPEN
    assert evaluate(sunday, datetime(2026, 10, 19, 1)).state is OpeningState.KNOWN_OPEN


def test_documented_google_always_open_representation():
    parsed = normalize([{"open": point(0, 0)}])
    assert parsed.validation_status is ScheduleValidationStatus.VALID
    assert evaluate(parsed, datetime(2026, 10, 21, 3)).state is OpeningState.KNOWN_OPEN


def test_missing_close_is_ambiguous_except_documented_always_open_shape():
    parsed = normalize([{"open": point(1, 9)}])
    assert parsed.validation_status is ScheduleValidationStatus.AMBIGUOUS
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.UNKNOWN


@pytest.mark.parametrize(
    ("value", "status"),
    [
        (None, ScheduleValidationStatus.MISSING),
        ({}, ScheduleValidationStatus.AMBIGUOUS),
        ({"periods": []}, ScheduleValidationStatus.AMBIGUOUS),
        ({"periods": "not-an-array"}, ScheduleValidationStatus.MALFORMED),
        ({"periods": [{"close": point(1, 10)}]}, ScheduleValidationStatus.MALFORMED),
    ],
)
def test_missing_and_malformed_schedules_are_not_open(value, status):
    parsed = normalize_google_regular_opening_hours(attraction_id=1, opening_hours=value)
    assert parsed.validation_status is status
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.UNKNOWN


@pytest.mark.parametrize(
    "open_point",
    [
        point(7, 9),
        point(-1, 9),
        point(1, 24),
        point(1, -1),
        point(1, 9, 60),
        {"day": True, "hour": 9, "minute": 0},
    ],
)
def test_invalid_google_point_values_are_rejected(open_point):
    parsed = normalize([{"open": open_point, "close": point(1, 17)}])
    assert parsed.validation_status is ScheduleValidationStatus.MALFORMED


def test_same_day_reverse_order_and_multi_day_span_are_rejected():
    reverse = normalize([{"open": point(1, 17), "close": point(1, 9)}])
    multi_day = normalize([{"open": point(1, 9), "close": point(3, 9)}])
    assert reverse.validation_status is ScheduleValidationStatus.MALFORMED
    assert multi_day.validation_status is ScheduleValidationStatus.UNSUPPORTED


def test_overlapping_periods_are_conflicting():
    parsed = normalize([
        {"open": point(1, 9), "close": point(1, 12)},
        {"open": point(1, 11), "close": point(1, 13)},
    ])
    assert parsed.validation_status is ScheduleValidationStatus.CONFLICTING
    assert evaluate(parsed, datetime(2026, 10, 19, 11, 30)).state is OpeningState.UNKNOWN


def test_open_now_is_ignored_and_input_is_not_mutated():
    raw = schedule([{"open": point(1, 9), "close": point(1, 17)}], open_now=False)
    original = deepcopy(raw)
    parsed = normalize_google_regular_opening_hours(attraction_id=1, opening_hours=raw)
    assert raw == original
    assert any("open_now was ignored" in warning for warning in parsed.warnings)
    assert evaluate(parsed, datetime(2026, 10, 19, 10)).state is OpeningState.KNOWN_OPEN


def test_timezone_aware_conversion_and_naive_rejection():
    parsed = normalize([{"open": point(1, 9), "close": point(1, 17)}])
    # 03:30 UTC is 09:00 in Asia/Colombo.
    assert evaluate_weekly_schedule(parsed, datetime(2026, 10, 19, 3, 30, tzinfo=timezone.utc)).state is OpeningState.KNOWN_OPEN
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_weekly_schedule(parsed, datetime(2026, 10, 19, 9))


def test_regular_weekly_result_explicitly_excludes_date_exceptions():
    parsed = normalize([{"open": point(1, 9), "close": point(1, 17)}])
    result = evaluate(parsed, datetime(2026, 10, 19, 10))
    assert OpeningReasonCode.DATE_EXCEPTIONS_NOT_CHECKED in result.reason_codes
    assert result.evidence_completeness == "regular_weekly_hours_only"


def test_time_context_request_requires_aware_datetime_and_valid_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeContextRequest(attraction_id=1, planned_visit_at=datetime(2026, 10, 19, 9))
    with pytest.raises(ValueError, match="IANA timezone"):
        TimeContextRequest(attraction_id=1, planned_visit_at=datetime(2026, 10, 19, 9, tzinfo=timezone.utc), timezone="SriLanka")


def test_normalized_output_is_stable_and_custom_provenance_is_preserved():
    raw = schedule([{"open": point(1, 9), "close": point(1, 17)}])
    evidence = TimingEvidence(
        source_type=TimingSourceType.OFFICIAL_OPERATOR,
        source_identifier="operator-schedule-42",
        source_url="https://example.invalid/hours",
        verification_status=VerificationStatus.MANUALLY_VERIFIED,
        freshness_status=FreshnessStatus.CURRENT,
    )
    first = normalize_google_regular_opening_hours(attraction_id=1, opening_hours=raw, evidence=evidence)
    second = normalize_google_regular_opening_hours(attraction_id=1, opening_hours=raw, evidence=evidence)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.evidence.source_identifier == "operator-schedule-42"
    assert first.evidence.source_url == "https://example.invalid/hours"


def test_default_provenance_explicitly_reports_missing_hours_retrieval_metadata():
    parsed = normalize([{"open": point(1, 9), "close": point(1, 17)}])
    assert parsed.evidence.retrieved_at is None
    assert parsed.evidence.freshness_status is FreshnessStatus.NOT_ASSESSED
    assert any("not independently stored" in item for item in parsed.evidence.limitations)
