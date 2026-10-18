from scripts.create_srilanka_tourism_gate5e2c2_reapproval_template import decisions


def test_reapproval_template_defaults_to_defer_and_preserves_hashes():
    rows = decisions([{"source_attraction_id": "official:1", "original_approval_hash": "old", "revised_proposal_sha256": "new", "district_evidence": {"district_name": "Galle"}, "conflicts": ["missing_verified_category"]}])
    assert rows[0]["decision"] == "DEFER"
    assert rows[0]["original_approval_hash"] == "old"
    assert rows[0]["revised_proposal_sha256"] == "new"
