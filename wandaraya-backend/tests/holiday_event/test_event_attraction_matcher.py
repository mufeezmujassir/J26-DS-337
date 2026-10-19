from types import SimpleNamespace

from app.holiday_event.event_attraction_matcher import EventAttractionCandidate, _event_text
from app.holiday_event.event_location_resolver import resolve_event_location


def make_event(**values):
    defaults = dict(id=1, title="WNPS Field Trip-Yala", description="Field trip", venue="Yala", category=None, organizer=None, event_notes=None, source_url="https://lankaevents.lk/iCalendar/?ID=7856", district_id=None, location_confidence="unresolved", address=None, city=None, province=None)
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_venue_mention_is_candidate_not_verified_location():
    location = resolve_event_location(make_event())
    assert location.verification_status == "CANDIDATE"
    assert location.latitude is None
    assert location.district_id is None


def test_missing_location_stays_unresolved():
    location = resolve_event_location(make_event(venue=None, description=None))
    assert location.verification_status == "UNRESOLVED"


def test_semantic_result_is_candidate_not_verified_link():
    candidate = EventAttractionCandidate(
        event_id=1, attraction_id=5, attraction_name="Yala National Park",
        semantic_similarity=0.82, semantic_candidate_rank=1,
        semantic_evidence_fields=["title", "venue"], matching_confidence=0.82,
        evidence_source_url="https://lankaevents.lk/iCalendar/?ID=7856",
        explanation="Semantic retrieval candidate only; it has not been verified as an event venue, location, or attraction identity.",
    )
    assert candidate.match_status == "CANDIDATE"
    assert "not been verified" in candidate.explanation
    assert "WNPS Field Trip-Yala" in _event_text(make_event())


def test_verified_district_source_evidence_has_no_fabricated_coordinates():
    location = resolve_event_location(make_event(district_id=12, location_confidence="source_explicit"))
    assert location.verification_status == "VERIFIED"
    assert location.district_id == 12
    assert location.latitude is None
