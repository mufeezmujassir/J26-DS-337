from types import SimpleNamespace
from datetime import date

from app.holiday_event.context_features import HolidayEventContextFeatureService, HolidayEventFeatureRequest


def event(*, event_id=1, source_url="https://source.test/event"):
    return SimpleNamespace(id=event_id, source_url=source_url)


def holiday(*, poya=False, public=False, bank=False):
    return SimpleNamespace(is_poya=poya, poya_name="Vesak" if poya else None, is_public_holiday=public, is_bank_holiday=bank, source_url="https://calendar.test/")


def attraction(*, coordinates=True):
    return SimpleNamespace(id=10, latitude=6.0 if coordinates else None, longitude=80.0 if coordinates else None)


def test_ordinary_date_has_no_context_score():
    result = HolidayEventContextFeatureService._feature(attraction(), [], [], [], [])
    assert result.is_poya_day is False
    assert result.holiday_context_score is None
    assert result.context_confidence == "unknown"


def test_poya_context_preserves_operational_uncertainty():
    result = HolidayEventContextFeatureService._feature(attraction(), ["Religious Heritage"], [holiday(poya=True, public=True)], [], [])
    assert result.is_poya_day is True
    assert result.is_public_holiday is None
    assert result.holiday_context_score == 0.6
    assert "opening hours are not verified" in result.explanation


def test_unresolved_event_location_has_no_false_proximity():
    result = HolidayEventContextFeatureService._feature(attraction(coordinates=False), [], [], [event()], [])
    assert result.overlapping_event_ids == [1]
    assert result.event_proximity_km is None
    assert result.event_context_score is None
    assert "event_location_unresolved_or_unmatched" in result.uncertainty_flags


def test_verified_link_is_separate_from_semantic_or_title_candidate():
    result = HolidayEventContextFeatureService._feature(attraction(), [], [], [event()], [(1, "https://verified.test/evidence", "verified", 1.0)])
    assert result.matched_event_ids == [1]
    assert result.event_proximity_km is None
    assert result.context_confidence == "high"


def test_semantic_candidate_stays_unverified_and_does_not_score_as_nearby():
    result = HolidayEventContextFeatureService._feature(attraction(), [], [], [event()], [(1, "https://source.test/event", "candidate", 0.8)])
    assert result.event_match_status == "candidate"
    assert result.event_context_score is None
    assert result.nearby_event_count is None
    assert "semantic_event_candidate_not_verified" in result.uncertainty_flags


def test_request_rejects_empty_candidate_batch():
    try:
        HolidayEventFeatureRequest(travel_date=date(2026, 5, 1), attraction_ids=[])
    except Exception:
        return
    raise AssertionError("empty attraction IDs must be rejected")


def test_request_accepts_public_interests_field_and_legacy_alias():
    current = HolidayEventFeatureRequest(travel_date=date(2026, 5, 1), attraction_ids=[1], interests=["heritage"])
    legacy = HolidayEventFeatureRequest(travel_date=date(2026, 5, 1), attraction_ids=[1], tourist_interests=["walking"])
    assert current.interests == ["heritage"]
    assert legacy.interests == ["walking"]
