from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.time_context.governance.catalogue_reconciliation import ExistingAttraction
from app.time_context.governance.google_places_reconciliation import Gate5DSettings, build_search_query, classify_result, consolidate_manifests, process_queue, score_candidate, source_is_compound, write_gate5d_reports
from app.time_context.governance.google_places_orchestrator import checkpoint


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


def test_locality_is_not_accepted_as_an_attraction():
    local = candidate(primaryType="locality", types=["locality", "political"], displayName={"text": "Inginiyagala"})
    result = classify_result(record(attraction_name="Senanayaka Samudraya of Inginiyagala"), [local], [], Gate5DSettings())
    assert result["classification"] == "related_locality_not_attraction"
    assert result["official_source_candidate_identity"] == "locality_only_result_not_identity_proof"


def test_delft_location_conflict_penalizes_colombo_candidate():
    good = candidate(id="places/delft", formattedAddress="Delft Island, Sri Lanka")
    wrong = candidate(id="places/colombo", formattedAddress="Colombo, Sri Lanka")
    assert score_candidate(record(attraction_name="Delft Dutch Fort"), good, [])["score"] > score_candidate(record(attraction_name="Delft Dutch Fort"), wrong, [])["score"]
    assert score_candidate(record(attraction_name="Delft Dutch Fort"), wrong, [])["location_conflict"]


def test_compound_source_never_inherits_kb_place_verification():
    result = classify_result(record(attraction_name="Arugambay & Pottuvil Point"), [candidate(id="places/exact")], existing("places/exact"), Gate5DSettings())
    assert source_is_compound("Arugambay & Pottuvil Point")
    assert result["google_candidate_kb_identity"] == "verified_existing_kb_place"
    assert result["official_source_candidate_identity"] == "compound_source_record_review_required"


def test_consolidation_deduplicates_and_marks_api_errors_retriable():
    queue = [record(external_source_id="one"), record(external_source_id="two")]
    complete = {"mode": "live", "results": [{"external_source_id": "one", "classification": "new_google_place_candidate", "candidates": [candidate(id="places/shared")]}]}
    failed = {"mode": "live", "results": [{"external_source_id": "two", "classification": "api_error", "candidates": []}]}
    output = consolidate_manifests(queue=queue, manifests=[complete, failed])
    assert output["completed_records"] == ["one"]
    assert output["retriable_records"] == ["two"]
    assert output["network_requests"] == 0 and output["postgresql_writes"] is False


def test_checkpoint_is_idempotent_and_plans_only_remaining_records(tmp_path: Path):
    queue_path = tmp_path / "queue.json"; queue_path.write_text(json.dumps({"records": [record(external_source_id="one"), record(external_source_id="two")]}))
    manifest = tmp_path / "stage_10_1_3e_gate5d_one_google_places_full_enrichment_manifest.json"
    summary = tmp_path / "stage_10_1_3e_gate5d_one_google_places_discovery_summary.json"
    manifest.write_text(json.dumps({"mode": "live", "results": [{"external_source_id": "one", "classification": "no_google_place_match", "candidates": []}]}))
    from hashlib import sha256
    summary.write_text(json.dumps({"queue_sha256": sha256(queue_path.read_bytes()).hexdigest()}))
    first = checkpoint(queue_path=queue_path, manifest_paths=[manifest]); second = checkpoint(queue_path=queue_path, manifest_paths=[manifest])
    assert first["completed_records"] == ["one"] == second["completed_records"]
    assert first["planned_batches"] == [["two"]]


def test_checkpoint_rejects_queue_sha_mismatch(tmp_path: Path):
    queue_path = tmp_path / "queue.json"; queue_path.write_text(json.dumps({"records": [record()]}))
    manifest = tmp_path / "stage_10_1_3e_gate5d_one_google_places_full_enrichment_manifest.json"; manifest.write_text(json.dumps({"mode":"live", "results": []}))
    summary = tmp_path / "stage_10_1_3e_gate5d_one_google_places_discovery_summary.json"; summary.write_text(json.dumps({"queue_sha256":"wrong"}))
    import pytest
    with pytest.raises(ValueError, match="SHA-256"):
        checkpoint(queue_path=queue_path, manifest_paths=[manifest])


def test_two_consecutive_manifests_advance_ten_without_duplicate_ids(tmp_path: Path):
    queue_path=tmp_path/"queue.json"; queue_path.write_text(json.dumps({"records":[record(external_source_id=str(i)) for i in range(10)]}))
    from hashlib import sha256
    paths=[]
    for name, ids in (("first", range(5)), ("second", range(5,10))):
        manifest=tmp_path/f"stage_10_1_3e_gate5d_{name}_google_places_full_enrichment_manifest.json"; summary=tmp_path/f"stage_10_1_3e_gate5d_{name}_google_places_discovery_summary.json"
        manifest.write_text(json.dumps({"mode":"live","results":[{"external_source_id":str(i),"classification":"no_google_place_match","candidates":[]} for i in ids]})); summary.write_text(json.dumps({"queue_sha256":sha256(queue_path.read_bytes()).hexdigest()})); paths.append(manifest)
    result=checkpoint(queue_path=queue_path,manifest_paths=paths)
    assert result["progress"]["completed"] == 10 and result["progress"]["remaining"] == 0


def test_reports_are_never_silently_overwritten(tmp_path: Path):
    queue_path=tmp_path/"queue.json"; queue_path.write_text(json.dumps({"records":[]}))
    write_gate5d_reports(results=[],usage={"mode":"offline"},queue_path=queue_path,reports_dir=tmp_path,batch_id="same")
    import pytest
    with pytest.raises(FileExistsError):
        write_gate5d_reports(results=[],usage={"mode":"offline"},queue_path=queue_path,reports_dir=tmp_path,batch_id="same")
