from types import SimpleNamespace

from scripts.sync_srilanka_tourism_gate5e2d2 import (
    canonical_hash,
    deterministic_payload,
    future_authorization_errors,
    vector_validation,
)


def record():
    return {
        "attraction_id": 6604, "name": "Example", "city": "Galle", "district": "Galle",
        "province": "Southern", "category_names": ["Heritage"], "activities": [],
        "district_id": 78, "latitude": 6.0, "longitude": 80.0, "google_place_id": "place",
        "semantic_document_sha256": "document", "source_attraction_id": "official:1",
    }


def test_payload_preserves_retriever_keys_and_adds_safe_metadata():
    payload = deterministic_payload(record(), [40])
    assert payload["attraction_id"] == 6604
    assert payload["categories"] == ["Heritage"]
    assert payload["category_ids"] == [40]
    assert payload["semantic_document_sha256"] == "document"


def test_vector_validation_requires_normalized_finite_1024_vector():
    valid = [1 / (1024 ** 0.5)] * 1024
    assert vector_validation(valid)["valid"] is True
    assert "non_finite_vector_value" in vector_validation([float("nan")] * 1024)["reasons"]
    assert "unexpected_dimension" in vector_validation([1.0])["reasons"]


def test_future_execution_needs_all_hashes_confirmation_and_snapshot():
    args = SimpleNamespace(confirm_execute=False, approved_count=None, scope_sha256=None,
                           plan_sha256=None, snapshot_name=None)
    errors = future_authorization_errors(args, "scope", "plan", {"existing_snapshots": []}, 24)
    assert {"missing_confirm_execute", "approved_count_mismatch", "scope_hash_mismatch", "plan_hash_mismatch", "missing_snapshot_name"} <= set(errors)


def test_canonical_hash_is_deterministic():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
