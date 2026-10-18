from scripts.sync_srilanka_tourism_gate5e2c3 import resolve_and_audit, validate_manifest


def action(source="official:1", **overrides):
    value = {"source_attraction_id": source, "approved_action": "INSERT_NEW_CANDIDATE", "original_approval_hash": "old", "revised_proposal_sha256": "new", "enrichment_evidence_sha256": "proof", "district_id": 78, "category_id": 36, "google_place_id": "google", "upstream_final_proposal_sha256": "up", "reviewer_decision": "APPROVE_INSERT_AFTER_CATEGORY_EVIDENCE", "reviewer_identity": "reviewer", "review_timestamp": "date", "review_notes": "notes"}
    value.update(overrides)
    return value


def evidence(source="official:1"):
    return {"source_attraction_id": source, "official_name": "Example Beach", "official_source_url": "https://srilanka.travel/a", "original_approval_hash": "old", "revised_proposal_sha256": "new", "enrichment_evidence_sha256": "proof", "district_evidence": {"status": "verified"}, "conflicts": ["district_derived_from_saved_gate5d_evidence_requires_reapproval"], "reapproval_required": True, "latitude": 6.0, "longitude": 80.0}


def test_manifest_validation_rejects_stale_and_blocked_actions():
    valid, invalid = validate_manifest(approved=[action()], enriched=[evidence()], upstream=[{"source_attraction_id": "official:1", "final_proposal_sha256": "up"}], validation={"blocked": []})
    assert len(valid) == 1 and not invalid
    valid, invalid = validate_manifest(approved=[action(revised_proposal_sha256="bad")], enriched=[evidence()], upstream=[{"source_attraction_id": "official:1", "final_proposal_sha256": "up"}], validation={"blocked": []})
    assert not valid and "revised_proposal_hash_mismatch" in invalid[0]["reasons"]


def test_collision_requires_review_not_an_automatic_link():
    payloads, audits = resolve_and_audit(valid=[{"action": action(), "evidence": evidence()}], prior={}, snapshot={"districts": {78: "Galle"}, "categories": {36: "Beach"}, "references": [], "attractions": [{"id": 9, "name": "Other", "google_place_id": "google", "district_id": 78, "latitude": 6.0, "longitude": 80.0}]}, batch_id="batch")
    assert not payloads
    assert audits[0]["classification"] == "EXISTING_ATTRACTION_REQUIRES_LINK_REVIEW"
