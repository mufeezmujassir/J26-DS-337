from scripts.verify_srilanka_tourism_gate5e2d6 import (
    EXPECTED_DIMENSION,
    IMPORTED_IDS,
    classify_semantic_response,
    compact_candidates,
    final_status,
)


def test_valid_semantic_response_is_accepted() -> None:
    result = {"http_status": 200, "body": [{"id": 6604, "semantic_score": 0.8}]}
    assert classify_semantic_response(result) == "passed"


def test_malformed_semantic_response_is_rejected() -> None:
    assert classify_semantic_response({"http_status": 200, "body": [{"id": "bad", "semantic_score": 0.2}]}) == "failed"
    assert classify_semantic_response({"http_status": 503, "body": {"detail": "unavailable"}}) == "failed"


def test_compact_candidates_preserves_identity_and_score() -> None:
    assert compact_candidates([{"id": 6604, "name": "Example", "semantic_score": 0.5}]) == [
        {"attraction_id": 6604, "name": "Example", "semantic_score": 0.5}
    ]


def test_imported_scope_is_exactly_24_stable_ids() -> None:
    assert IMPORTED_IDS == list(range(6604, 6628))
    assert EXPECTED_DIMENSION == 1024


def test_recovery_readiness_requires_visible_snapshot_after_semantic_success() -> None:
    assert final_status(semantic_verified=True, recovery_snapshot_visible=False) == "SEMANTIC_SEARCH_VERIFIED"
    assert final_status(semantic_verified=True, recovery_snapshot_visible=True) == "READY_FOR_RECOMMENDATION_BASELINE"
