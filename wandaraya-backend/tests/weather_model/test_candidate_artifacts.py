from datetime import date
from pathlib import Path

import pytest

from app.weather_model.backtesting.rolling_origin import add_months
from app.weather_model.backtesting.schemas import MonthlyObservation
from app.weather_model.training.candidate_artifacts import (
    create_candidate_artifact,
    load_candidate_artifact,
    prepare_candidate_training,
)
from app.weather_model.training.train_candidates import failure_category


def observations(count=36, missing=None):
    return [
        MonthlyObservation(
            month=add_months(date(2021, 1, 1), index),
            value=None if add_months(date(2021, 1, 1), index) == missing else float(20 + index),
        )
        for index in range(count)
    ]


def test_temperature_uses_documented_training_only_imputation() -> None:
    training, provenance = prepare_candidate_training(
        observations(missing=date(2022, 5, 1)), target="temperature_min_c"
    )
    assert len(training) == 36
    assert all(item.value is not None for item in training)
    assert provenance["imputed_training_months"] == 1
    assert provenance["training_policy"]["name"] == "missing_aware_training_only"


def test_rainfall_never_interpolates_missing_observations() -> None:
    with pytest.raises(ValueError, match="no imputation"):
        prepare_candidate_training(
            observations(missing=date(2022, 5, 1)), target="rainfall_mm"
        )


def test_climatology_artifact_is_versioned_and_checksum_verified(tmp_path: Path) -> None:
    training, provenance = prepare_candidate_training(observations(), target="rainfall_mm")
    manifest = create_candidate_artifact(
        root=tmp_path / "one",
        district_id=78,
        target="rainfall_mm",
        model_name="monthly_climatology",
        training=training,
        provenance=provenance,
        registry_evidence_fingerprint="evidence-fingerprint",
    )
    loaded, payload = load_candidate_artifact(
        Path(manifest["artifact_path"]).parent / "manifest.json"
    )
    assert loaded["artifact_version"] == manifest["artifact_version"]
    assert payload
    assert loaded["production_approved"] is False

    repeated = create_candidate_artifact(
        root=tmp_path / "two",
        district_id=78,
        target="rainfall_mm",
        model_name="monthly_climatology",
        training=training,
        provenance=provenance,
        registry_evidence_fingerprint="evidence-fingerprint",
    )
    assert repeated["artifact_version"] == manifest["artifact_version"]
    with pytest.raises(FileExistsError, match="will not be overwritten"):
        create_candidate_artifact(
            root=tmp_path / "one",
            district_id=78,
            target="rainfall_mm",
            model_name="monthly_climatology",
            training=training,
            provenance=provenance,
            registry_evidence_fingerprint="evidence-fingerprint",
        )


def test_checksum_mismatch_is_detected(tmp_path: Path) -> None:
    training, provenance = prepare_candidate_training(observations(), target="rainfall_mm")
    manifest = create_candidate_artifact(
        root=tmp_path,
        district_id=78,
        target="rainfall_mm",
        model_name="monthly_climatology",
        training=training,
        provenance=provenance,
        registry_evidence_fingerprint="evidence-fingerprint",
    )
    artifact = Path(manifest["artifact_path"])
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_candidate_artifact(artifact.parent / "manifest.json")


def test_training_summary_categories_do_not_count_reuse_as_failure() -> None:
    assert failure_category(FileExistsError("exists")) == "existing_artifact"
    assert failure_category(ValueError("Rainfall training requires complete verified observations; no imputation is allowed.")) == "insufficient_data"
    assert failure_category(RuntimeError("unexpected")) == "execution_failure"
