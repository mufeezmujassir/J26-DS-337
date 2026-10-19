from scripts.finalize_srilanka_tourism_gate5e2c4 import build_reports
from scripts.sync_srilanka_tourism_gate5e2c3 import digest

def test_scope_excludes_existing_identity_collision():
    action={"source_attraction_id":"official:1","approved_action":"INSERT_NEW_CANDIDATE","original_approval_hash":"old","revised_proposal_sha256":"new","enrichment_evidence_sha256":"proof","district_id":1,"category_id":2,"google_place_id":"p","upstream_final_proposal_sha256":"up","reviewer_decision":"APPROVE_INSERT_AFTER_CATEGORY_EVIDENCE","reviewer_identity":"r","review_timestamp":"x","review_notes":"n"}
    evidence={"source_attraction_id":"official:1","official_name":"Name","official_source_url":"https://srilanka.travel/a","original_approval_hash":"old","revised_proposal_sha256":"new","enrichment_evidence_sha256":"proof","district_evidence":{"status":"verified"},"conflicts":["district_derived_from_saved_gate5d_evidence_requires_reapproval"],"reapproval_required":True,"latitude":6.0,"longitude":80.0}
    reports=build_reports(approved=[action],enriched=[evidence],upstream=[{"source_attraction_id":"official:1","final_proposal_sha256":"up"}],validation={"blocked":[]},prior={},snapshot={"districts":{1:"D"},"categories":{2:"C"},"references":[],"attractions":[{"id":4,"name":"Existing","google_place_id":"p","district_id":1,"latitude":6,"longitude":80}]},batch_id="b",manifest_sha="m")
    assert reports["summary"]["ready_insertions"] == 0
    assert reports["summary"]["conflicting_source_attraction_ids"] == ["official:1"]
    assert reports["transaction_safety_validation"]["qdrant_writes_executed"] is False
