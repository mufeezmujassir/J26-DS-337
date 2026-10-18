from __future__ import annotations

from scripts.plan_srilanka_tourism_gate5e2c1 import audit_manifest, plan_operations


def proposal(source="source:1"):
    return {"source_attraction_id": source, "final_proposal_sha256": "proposal", "proposed_action": "INSERT_NEW_CANDIDATE"}


def approved(source="source:1"):
    return {"source_attraction_id": source, "approved_action": "INSERT_NEW_CANDIDATE", "final_proposal_sha256": "proposal", "checkpoint_sha256": "checkpoint", "reviewer_identity": "reviewer", "review_timestamp": "2026-10-17T10:00:00+05:30", "review_notes": "reviewed"}


def test_manifest_duplicate_source_ids_are_detected():
    result = audit_manifest(manifest={"checkpoint_sha256": "checkpoint", "records": [approved(), approved()]}, proposals=[proposal()], validation={"approved_actions": [approved()]}, checkpoint={})
    assert result["duplicate_source_attraction_ids"] == ["source:1"]


def test_stale_hash_is_quarantined_by_integrity_audit():
    record = approved(); record["final_proposal_sha256"] = "stale"
    result = audit_manifest(manifest={"checkpoint_sha256": "checkpoint", "records": [record]}, proposals=[proposal()], validation={"approved_actions": [record]}, checkpoint={})
    assert "stale_or_modified_proposal" in result["invalid_records"][0]["reasons"]


def test_missing_insertion_fields_are_quarantined_in_dry_run():
    records = [{"record": approved(), "reasons": []}]
    planned, quarantined = plan_operations(valid_records=records, evidence=[{"source_attraction_id": "source:1", "official_attraction_identity": "Name", "google_candidate_identity": "place", "existing_kb_target_attraction_id": None, "source_provenance": {"official_source_url": "https://example.test"}}], duplicate_clusters={"clusters": []})
    assert planned == []
    assert "missing_verified_district" in quarantined[0]["quarantine_reasons"]


def test_unresolved_cluster_is_quarantined():
    records = [{"record": approved(), "reasons": []}]
    _planned, quarantined = plan_operations(valid_records=records, evidence=[{"source_attraction_id": "source:1", "official_attraction_identity": "Name", "google_candidate_identity": "place", "existing_kb_target_attraction_id": None, "source_provenance": {"official_source_url": "https://example.test"}}], duplicate_clusters={"clusters": [{"source_attraction_ids": ["source:1"], "resolution": "PENDING_REVIEW"}]})
    assert "unresolved_duplicate_cluster" in quarantined[0]["quarantine_reasons"]
