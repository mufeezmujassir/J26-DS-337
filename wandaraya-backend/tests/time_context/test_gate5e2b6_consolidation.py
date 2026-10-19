from __future__ import annotations

from scripts.consolidate_srilanka_tourism_gate5e2b6 import proposals, validate_decisions, verification_audit


def record(source_id="source:1"):
    return {"source_attraction_id": source_id, "candidate_verification_result": "NO_VALID_GOOGLE_CANDIDATE"}


def proposal(source_id="source:1", action="INSERT_NEW_CANDIDATE"):
    return {"source_attraction_id": source_id, "proposed_action": action, "final_proposal_sha256": "proposal-hash"}


def test_incomplete_verification_blocks_finalization():
    audit = verification_audit([record()], {"completed_source_ids": [], "failed_source_ids": [], "results": [], "cumulative_requests": 0})
    assert audit["verification_complete"] is False
    assert audit["finalization_blocked"] is True


def test_completed_evidence_makes_targeted_audit_complete():
    audit = verification_audit([record()], {"completed_source_ids": ["source:1"], "failed_source_ids": [], "results": [{"source_attraction_id": "source:1"}], "cumulative_requests": 2})
    assert audit["verification_complete"] is True


def test_missing_reviewer_identity_blocks_approval():
    result = validate_decisions(decisions={"decisions": [{"source_attraction_id": "source:1", "decision": "APPROVE_INSERT", "checkpoint_sha256": "checkpoint", "final_proposal_sha256": "proposal-hash", "reviewer_identity": None, "review_timestamp": "2026-10-17T10:00:00+05:30", "review_notes": "checked"}]}, plan=[proposal()], checkpoint_hash="checkpoint", audit={"verification_complete": True})
    assert result["blocked_actions"][0]["reason"] == "reviewer_identity_required"


def test_stale_proposal_hash_is_rejected():
    result = validate_decisions(decisions={"decisions": [{"source_attraction_id": "source:1", "decision": "APPROVE_INSERT", "checkpoint_sha256": "checkpoint", "final_proposal_sha256": "stale", "reviewer_identity": "reviewer", "review_timestamp": "2026-10-17T10:00:00+05:30", "review_notes": "checked"}]}, plan=[proposal()], checkpoint_hash="checkpoint", audit={"verification_complete": True})
    assert result["blocked_actions"][0]["reason"] == "stale_or_modified_proposal"


def test_empty_decisions_make_valid_empty_manifest_input():
    result = validate_decisions(decisions={"decisions": []}, plan=[proposal()], checkpoint_hash="checkpoint", audit={"verification_complete": False})
    assert result["approved_actions"] == []
    assert result["writes"] is False


def test_completed_verification_does_not_reset_valid_insert_or_link():
    audit = {"verification_complete": True}
    records = [{"source_attraction_id": "source:insert", "corrected_proposed_action": "INSERT_NEW_CANDIDATE", "v5_proposal_sha256": "one"}, {"source_attraction_id": "source:link", "corrected_proposed_action": "LINK_SOURCE_REFERENCE_CANDIDATE", "v5_proposal_sha256": "two"}]
    evidence = {"source:link": {"existing_kb_target_attraction_id": 42, "existing_kb_name_match_ids": [42], "source_provenance": {"official_source_url": "https://example.test/link"}}}
    assert [item["proposed_action"] for item in proposals(records, audit, evidence)] == ["INSERT_NEW_CANDIDATE", "LINK_SOURCE_REFERENCE_CANDIDATE"]
