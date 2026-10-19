from types import SimpleNamespace

from scripts.sync_srilanka_tourism_gate5e2d1 import (
    classify_point,
    document_hash,
    point_id_for_attraction,
    validate_document,
    vector_config_audit,
)


def point(point_id, attraction_id, document_hash_value=None):
    payload = {"attraction_id": attraction_id}
    if document_hash_value is not None:
        payload["semantic_document_sha256"] = document_hash_value
    return SimpleNamespace(id=point_id, payload=payload)


def test_document_hash_is_deterministic_and_point_identity_is_stable():
    assert document_hash("Sigiriya") == document_hash("Sigiriya")
    assert point_id_for_attraction(6604) == 6604


def test_document_validation_rejects_missing_governance_evidence():
    failures, optional = validate_document(
        name="A", text="Attraction: A\n\nLocation: Galle, Sri Lanka", district="Galle",
        categories=["Heritage"], latitude=6.0, longitude=80.0,
        source_reference_count=0, provenance_count=0,
    )
    assert "missing_or_duplicate_official_source_reference" in failures
    assert "missing_field_provenance" in failures
    assert "verified_description" in optional


def test_existing_point_without_document_hash_is_stale_not_current():
    result = classify_point(attraction_id=6604, expected_hash="new", points=[point(6604, 6604)])
    assert result["classification"] == "EXISTING_VECTOR_STALE"


def test_duplicate_or_wrong_point_identity_is_a_conflict():
    duplicate = classify_point(attraction_id=6604, expected_hash="hash", points=[
        point(6604, 6604, "hash"), point(999, 6604, "hash"),
    ])
    wrong = classify_point(attraction_id=6604, expected_hash="hash", points=[point(6604, 12, "hash")])
    assert duplicate["classification"] == "VECTOR_IDENTITY_CONFLICT"
    assert wrong["classification"] == "VECTOR_IDENTITY_CONFLICT"


def test_vector_schema_requires_existing_unnamed_bge_cosine_space():
    good = SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
        vectors=SimpleNamespace(size=1024, distance=SimpleNamespace(value="Cosine"))
    )))
    bad = SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors={"text": object()})))
    assert vector_config_audit(good)["compatible"] is True
    assert vector_config_audit(bad)["compatible"] is False
