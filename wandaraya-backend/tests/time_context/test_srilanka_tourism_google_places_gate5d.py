from __future__ import annotations

import asyncio

from app.time_context.governance.catalogue_reconciliation import ExistingAttraction
from app.time_context.governance.google_places_reconciliation import Gate5DSettings, build_search_query, classify_result, process_queue, score_candidate


def existing(place_id=None):
    return [ExistingAttraction(1, "Dambulla Cave Temple", None, place_id, None, None, None, None, None, (), ("Dambulla Cave Temple",), ())]


def record(**overrides):
    base = {"external_source_id": "srilanka_tourism_attraction:36", "attraction_name": "Dambulla CaveTemple", "source_url": "https://srilanka.travel/attraction?attraction_id=36", "district": "Matale", "latitude": None, "longitude": None}
    base.update(overrides); return base


def candidate(**overrides):
    base = {"id": "places/abc", "displayName": {"text": "Dambulla Cave Temple"}, "formattedAddress": "Matale, Sri Lanka", "types": ["tourist_attraction"]}
    base.update(overrides); return base


def test_query_uses_only_supported_locality():
    assert build_search_query(record()) == "Dambulla CaveTemple, Matale, Sri Lanka"
    assert build_search_query(record(district=None)) == "Dambulla CaveTemple, Sri Lanka"


def test_exact_existing_google_place_id_is_verified():
    result = classify_result(record(), [candidate(id="places/exact")], existing("places/exact"), Gate5DSettings())
    assert result["classification"] == "verified_existing_kb_match"
    assert result["candidates"][0]["component_scores"]["existing_google_place_id"] == 1.0


def test_name_similarity_is_review_not_verification():
    result = classify_result(record(), [candidate()], existing(), Gate5DSettings(high_confidence_threshold=0.85))
    assert result["classification"] == "high_confidence_candidate_review"


def test_ambiguous_candidates_are_not_merged():
    result = classify_result(record(), [candidate(id="places/a"), candidate(id="places/b")], [], Gate5DSettings())
    assert result["classification"] == "ambiguous_multiple_candidates"


def test_no_google_results_and_null_fields_are_preserved():
    result = classify_result(record(), [], [], Gate5DSettings())
    assert result["classification"] == "no_google_place_match"
    assert result["details"] is None


def test_proximity_is_not_invented_when_source_coordinates_missing():
    scored = score_candidate(record(), candidate(location={"latitude": 7.86, "longitude": 80.65}), [],)
    assert scored["distance_km"] is None
    assert scored["component_scores"]["geographic_proximity"] == 0.0


def test_offline_mode_has_no_network_calls():
    class ExplodingClient:
        async def text_search(self, **kwargs): raise AssertionError("offline must not call network")
        async def get_place_details(self, *args): raise AssertionError("offline must not call network")
    results, usage = asyncio.run(process_queue(queue=[record()], existing=[], settings=Gate5DSettings(), client=ExplodingClient(), live=False))
    assert usage["network_requests"] == 0
    assert results[0]["classification"] == "insufficient_evidence"


def test_live_api_failure_is_explicit_and_bounded():
    class FailingClient:
        calls = 0
        async def text_search(self, **kwargs): self.calls += 1; raise RuntimeError("quota")
        async def get_place_details(self, *args): raise AssertionError
    client = FailingClient()
    results, usage = asyncio.run(process_queue(queue=[record()], existing=[], settings=Gate5DSettings(max_retries=1), client=client, live=True))
    assert results[0]["classification"] == "api_error"
    assert client.calls == 2
    assert usage["network_requests"] == 1
