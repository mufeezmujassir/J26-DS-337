from scripts.validate_srilanka_tourism_gate5e2c2_reapprovals import APPROVAL, validate


def record():
    return {
        "source_attraction_id": "official:1", "original_approval_hash": "old", "revised_proposal_sha256": "new",
        "enrichment_evidence_sha256": "evidence", "district_id": 78, "category_id": 36,
        "district_evidence": {"status": "verified"},
        "conflicts": ["district_derived_from_saved_gate5d_evidence_requires_reapproval"], "reapproval_required": True,
    }


def decision(**overrides):
    value = {
        "source_attraction_id": "official:1", "original_approval_hash": "old", "revised_proposal_sha256": "new",
        "decision": APPROVAL, "reviewer_identity": "reviewer", "review_timestamp": "2026-10-17T18:00:00+05:30",
        "review_notes": "Reviewed official source, saved Google evidence, district boundary, and category.",
    }
    value.update(overrides)
    return value


def upstream():
    return [{"source_attraction_id": "official:1", "approved_action": "INSERT_NEW_CANDIDATE", "final_proposal_sha256": "upstream"}]


def test_reapproval_accepts_only_explicit_hash_bound_complete_decision():
    outcome = validate(enriched=[record()], decisions=[decision()], upstream=upstream())
    assert len(outcome["approved"]) == 1
    assert not outcome["blocked"]


def test_reapproval_rejects_defer_stale_hash_and_unresolved_identity():
    deferred = validate(enriched=[record()], decisions=[decision(decision="DEFER")], upstream=upstream())
    assert "not_explicitly_reapproved" in deferred["blocked"][0]["reasons"]
    stale = validate(enriched=[record()], decisions=[decision(revised_proposal_sha256="changed")], upstream=upstream())
    assert "stale_or_modified_revised_proposal_hash" in stale["blocked"][0]["reasons"]
    unresolved = record(); unresolved["conflicts"].append("unresolved_duplicate_cluster")
    rejected = validate(enriched=[unresolved], decisions=[decision()], upstream=upstream())
    assert "unresolved_duplicate_cluster" in rejected["blocked"][0]["reasons"]
