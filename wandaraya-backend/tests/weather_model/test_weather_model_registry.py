from pathlib import Path

import pytest

from app.weather_model.registry.registry_manager import RegistryManager
from app.weather_model.registry.schemas import ApprovalRequest


def source(
    *,
    status="eligible_for_review",
    flags=None,
    candidate="prophet",
) -> dict:
    return {
        "district_id": 78,
        "target": "temperature_max_c",
        "evidence_status": status,
        "review_flags": flags or [],
        "provisional_candidate": candidate,
        "model_metrics": {
            "monthly_climatology": {"mae": 0.6, "rmse": 0.7, "bias": 0.1},
            "seasonal_naive": {"mae": 0.7, "rmse": 0.8, "bias": 0.1},
            "prophet": {"mae": 0.5, "rmse": 0.6, "bias": 0.1},
        },
        "paired_prediction_validation": {"paired_observed_targets_valid": True},
    }


def validation(series: list[dict]) -> dict:
    return {"series": series}


def test_registry_creation_is_pending_and_unapproved(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source(), {**source(), "district_id": 74, "target": "rainfall_mm", "evidence_status": "insufficient_evidence", "provisional_candidate": None}]))
    manager.save(registry)

    loaded = manager.load()
    assert loaded is not None
    assert len(loaded.entries) == 2
    assert all(entry.approval_status == "pending_review" for entry in loaded.entries)
    assert not loaded.production_approved
    assert len(loaded.audit_events) == 2


def test_insufficient_evidence_and_unresolved_bias_cannot_be_approved(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    insufficient = manager.build_from_validation(validation([source(status="insufficient_evidence", candidate=None)]))
    with pytest.raises(ValueError, match="Insufficient evidence"):
        manager.approve(insufficient, 78, "temperature_max_c", ApprovalRequest(reviewer_id="reviewer", selected_model="prophet", justification="reviewed"))

    biased = manager.build_from_validation(validation([source(flags=["selected_model_has_large_systematic_bias"])]))
    with pytest.raises(ValueError, match="Unresolved review flags"):
        manager.approve(biased, 78, "temperature_max_c", ApprovalRequest(reviewer_id="reviewer", selected_model="prophet", justification="reviewed"))


def test_explicit_approval_requires_and_records_manual_decision(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source()]))
    manager.approve(registry, 78, "temperature_max_c", ApprovalRequest(reviewer_id="researcher-1", selected_model="prophet", justification="Metrics and paired targets reviewed."))
    entry = registry.entries[0]

    assert entry.approval_status == "approved"
    assert entry.production_approved is True
    assert entry.approved_by == "researcher-1"
    assert registry.audit_events[-1].action == "approved"
    with pytest.raises(ValueError, match="already approved"):
        manager.approve(registry, 78, "temperature_max_c", ApprovalRequest(reviewer_id="researcher-2", selected_model="prophet", justification="duplicate"))


def test_evidence_change_invalidates_prior_approval_and_preserves_audit_history(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source()]))
    manager.approve(registry, 78, "temperature_max_c", ApprovalRequest(reviewer_id="researcher", selected_model="prophet", justification="reviewed"))
    manager.save(registry)

    changed = source()
    changed["model_metrics"]["prophet"]["mae"] = 0.9
    rebuilt = manager.build_from_validation(validation([changed]))

    assert rebuilt.entries[0].approval_status == "pending_review"
    assert rebuilt.entries[0].production_approved is False
    assert rebuilt.entries[0].selected_model is None
    assert [event.action for event in rebuilt.audit_events][-1] == "evidence_changed"
    assert any(event.action == "approved" for event in rebuilt.audit_events)


def test_unchanged_evidence_preserves_manual_decision(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    original = validation([source()])
    registry = manager.build_from_validation(original)
    manager.approve(registry, 78, "temperature_max_c", ApprovalRequest(reviewer_id="researcher", selected_model="prophet", justification="reviewed"))
    manager.save(registry)

    rebuilt = manager.build_from_validation(original)
    assert rebuilt.entries[0].approval_status == "approved"
    assert rebuilt.entries[0].selected_model == "prophet"
    assert rebuilt.entries[0].production_approved is True


def test_artifact_change_requires_revalidation(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source()]))
    manager.approve(registry, 78, "temperature_max_c", ApprovalRequest(reviewer_id="researcher", selected_model="prophet", justification="reviewed"))

    manager.record_artifact_change(registry, 78, "temperature_max_c", model_version="prophet-v2", artifact_path="data/weather/models/prophet-v2.bin", reason="Retrained with updated historical data.")
    entry = registry.entries[0]
    assert entry.approval_status == "pending_review"
    assert entry.production_approved is False
    assert entry.model_version == "prophet-v2"
    assert registry.audit_events[-1].action == "artifact_changed"


def test_candidate_artifact_registration_does_not_approve_model(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source()]))
    manager.register_candidate_artifact(
        registry,
        78,
        "temperature_max_c",
        model_name="prophet",
        model_version="candidate-version",
        artifact_path="data/weather/artifacts/candidate.json",
        checksum_sha256="abc123",
    )
    entry = registry.entries[0]
    assert entry.approval_status == "pending_review"
    assert entry.production_approved is False
    assert entry.candidate_artifacts["prophet"]["model_version"] == "candidate-version"
    assert registry.audit_events[-1].action == "artifact_registered"


def test_rejection_is_audited(tmp_path: Path) -> None:
    manager = RegistryManager(tmp_path / "registry.json")
    registry = manager.build_from_validation(validation([source()]))
    manager.reject(registry, 78, "temperature_max_c", reviewer_id="reviewer", reason="Awaiting additional bias analysis.")

    assert registry.entries[0].approval_status == "rejected"
    assert registry.entries[0].production_approved is False
    assert registry.audit_events[-1].action == "rejected"
