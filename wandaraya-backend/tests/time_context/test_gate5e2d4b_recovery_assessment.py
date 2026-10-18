from scripts.sync_srilanka_tourism_gate5e2d4b import classify_recovery_log


def test_malformed_wal_restore_is_not_reported_as_success():
    result = classify_recovery_log(
        "Recovering snapshot\nFailed to read first-index file: Failed to deserialize first-index"
    )
    assert result["result"] == "restore_failed_malformed_wal"
    assert result["snapshot_restore_completed"] is False


def test_listening_log_is_a_successful_restore_signal():
    result = classify_recovery_log("Recovering snapshot\nQdrant HTTP listening on 6333")
    assert result["result"] == "restore_succeeded"


def test_unrelated_log_remains_inconclusive():
    assert classify_recovery_log("container started")["result"] == "inconclusive"
