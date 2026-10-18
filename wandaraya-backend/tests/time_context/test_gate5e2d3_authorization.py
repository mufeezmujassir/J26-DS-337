from scripts.sync_srilanka_tourism_gate5e2d3 import executor_audit, validate_d2
from scripts.sync_srilanka_tourism_gate5e2d2 import canonical_hash


def d2_fixture():
    ids = list(range(6604, 6628))
    plan = {"collection": "sri_lanka_attractions", "point_ids": ids, "scope_sha256": "scope", "embedding_model": "BAAI/bge-large-en-v1.5", "vector_dimension": 1024}
    plan["plan_sha256"] = canonical_hash(plan)
    return {
        "summary": {"postgresql_attraction_count": 6120, "scope_sha256": "scope", "identity_conflicts": 0},
        "scope": {"records": [{"attraction_id": value} for value in ids]},
        "documents": {"records": [{"document_hash_matches_d1": True} for _ in ids]},
        "embeddings": {"embeddings": [{"valid": True, "dimension": 1024, "model_name": "BAAI/bge-large-en-v1.5"} for _ in ids]},
        "identity": {"records": [{"classification": "MISSING_VECTOR"} for _ in ids]},
        "plan": plan,
    }


def test_d2_integrity_accepts_exact_scope_and_valid_evidence():
    ids, failures = validate_d2(d2_fixture())
    assert ids == list(range(6604, 6628))
    assert failures == []


def test_d2_integrity_rejects_changed_document_or_scope():
    value = d2_fixture()
    value["documents"]["records"][0]["document_hash_matches_d1"] = False
    value["scope"]["records"].pop()
    _, failures = validate_d2(value)
    assert "semantic_document_hash_integrity_failed" in failures
    assert "approved_import_scope_is_not_exactly_6604_to_6627" in failures


def test_executor_contains_required_authorization_gates():
    assert executor_audit()["all_required_executor_checks_pass"] is True
