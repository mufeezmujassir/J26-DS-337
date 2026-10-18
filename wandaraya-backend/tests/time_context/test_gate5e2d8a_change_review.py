from scripts.review_qdrant_snapshot_change_gate5e2d8a import proposed_diff


def test_minimal_diff_adds_snapshot_mount_only() -> None:
    diff = proposed_diff()
    assert "/qdrant/snapshots" in diff
    assert "/qdrant/storage" in diff
    assert diff.count("+") >= 2
    assert "qdrant-data-quarantine" not in diff
