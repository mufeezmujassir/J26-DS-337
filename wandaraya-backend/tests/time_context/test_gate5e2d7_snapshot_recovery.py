from scripts.prepare_qdrant_snapshot_recovery_gate5e2d7 import (
    MINIMUM_SAFETY_MARGIN_BYTES,
    recovery_target_is_isolated,
    safe_snapshot_directory,
    storage_requirement,
)


def test_snapshot_directory_rejects_active_or_quarantine_data_paths() -> None:
    assert safe_snapshot_directory("qdrant-replacement-snapshots")
    assert not safe_snapshot_directory("qdrant-data")
    assert not safe_snapshot_directory("qdrant-data-quarantine-2026-10-18")
    assert not safe_snapshot_directory("../outside")


def test_storage_plan_requires_export_recovery_copy_and_margin() -> None:
    assert storage_requirement(100) == (200 + MINIMUM_SAFETY_MARGIN_BYTES)


def test_recovery_target_must_not_reuse_production_container_or_volume() -> None:
    assert recovery_target_is_isolated(
        container="recovery", volume="recovery-volume", production_container="production", production_volume="production-volume"
    )
    assert not recovery_target_is_isolated(
        container="production", volume="recovery-volume", production_container="production", production_volume="production-volume"
    )
    assert not recovery_target_is_isolated(
        container="recovery", volume="production-volume", production_container="production", production_volume="production-volume"
    )
