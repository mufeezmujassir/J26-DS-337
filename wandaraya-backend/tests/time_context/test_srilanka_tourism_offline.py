from datetime import date

import pytest

from app.time_context.governance.srilanka_tourism import (
    EntityMatchDecision, ExistingEntityCandidate, PermissionEvidenceStatus, SriLankaTourismPermission,
    TourismPageType, extract_fixture, match_entity, normalize_explicit_official_hours,
)


def attraction_fixture(**extra):
    return {"source_url": "https://srilanka.travel/example", "name": "Sample Fort", "location_text": "Galle", "description": "Provided fixture text", **extra}


def test_verbal_permission_is_not_misrepresented_as_written_or_automated_authorisation():
    permission = SriLankaTourismPermission()
    assert permission.evidence_status is PermissionEvidenceStatus.UNDOCUMENTED
    assert not permission.automated_fetch_allowed and not permission.persistent_storage_allowed and not permission.embeddings_allowed


def test_invalid_domains_unknown_fields_and_missing_fields_are_handled_without_network():
    with pytest.raises(ValueError, match="approved"):
        extract_fixture({"source_url": "https://example.com/x"}, TourismPageType.ATTRACTION)
    record = extract_fixture(attraction_fixture(unrecognised="ignored"), TourismPageType.ATTRACTION)
    assert record.entrance_fee is None and record.extraction_warnings


def test_event_and_holiday_dates_are_typed_and_not_inferred():
    event = extract_fixture({"source_url": "https://srilanka.travel/event", "name": "Festival", "event_date": "2026-12-01"}, TourismPageType.EVENT)
    holiday = extract_fixture({"source_url": "https://srilanka.travel/holiday", "name": "Holiday", "holiday_date": "2026-12-25"}, TourismPageType.PUBLIC_HOLIDAY)
    assert event.event_date == date(2026, 12, 1) and holiday.holiday_date == date(2026, 12, 25)
    with pytest.raises(Exception): extract_fixture({"source_url": "https://srilanka.travel/holiday", "holiday_date": "not-a-date"}, TourismPageType.PUBLIC_HOLIDAY)


def test_entity_matching_is_conservative_and_never_inserts():
    record = extract_fixture(attraction_fixture(), TourismPageType.ATTRACTION)
    one = match_entity(record, [ExistingEntityCandidate(attraction_id=1, name="sample fort", location_text="Galle")])
    many = match_entity(record, [ExistingEntityCandidate(attraction_id=1, name="sample fort", location_text="Galle"), ExistingEntityCandidate(attraction_id=2, name="sample fort", location_text="Galle")])
    none = match_entity(record, [])
    assert one.decision is EntityMatchDecision.EXISTING_MATCH
    assert many.decision is EntityMatchDecision.AMBIGUOUS_MATCH
    assert none.decision is EntityMatchDecision.PROPOSED_NEW_ENTITY


def test_only_explicit_fixture_hours_are_normalised_and_missing_hours_stay_unknown():
    record = extract_fixture(attraction_fixture(opening_hours={"periods": [{"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 17, "minute": 0}}]}), TourismPageType.OPERATING_INFORMATION)
    assert normalize_explicit_official_hours(attraction_id=1, record=record).validation_status.value == "valid"
    assert normalize_explicit_official_hours(attraction_id=1, record=extract_fixture(attraction_fixture(), TourismPageType.ATTRACTION)) is None
