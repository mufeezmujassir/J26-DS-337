from datetime import date, datetime, timezone
from pathlib import Path

from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult
from app.weather_model.forecasting.forecast_service import ForecastService
from app.weather_model.registry.registry_manager import RegistryManager
from app.weather_model.registry.schemas import RegistryEntry, WeatherModelRegistry
from app.weather_model.training.candidate_artifacts import (
    create_candidate_artifact,
    prepare_candidate_training,
)
from app.weather_model.backtesting.rolling_origin import add_months
from app.weather_model.backtesting.schemas import MonthlyObservation


class LiveClient:
    def __init__(self, result):
        self.result = result

    def get_forecast(self, **_kwargs):
        return self.result


def observations():
    return [
        MonthlyObservation(add_months(date(2021, 1, 1), index), float(20 + index))
        for index in range(36)
    ]


def approved_registry(tmp_path: Path, *, approved=True, evidence_fingerprint="evidence") -> tuple[Path, dict]:
    training, provenance = prepare_candidate_training(observations(), target="temperature_max_c")
    manifest = create_candidate_artifact(
        root=tmp_path / "artifacts", district_id=78, target="temperature_max_c",
        model_name="monthly_climatology", training=training, provenance=provenance,
        registry_evidence_fingerprint="evidence",
    )
    entry = RegistryEntry(
        district_id=78, target="temperature_max_c", recommended_model="monthly_climatology",
        selected_model="monthly_climatology" if approved else None,
        evidence_status="eligible_for_review", review_flags=[], metrics_by_model={"monthly_climatology": {"mae": 0.5}},
        validation_report_path="validation.json", validation_evidence={"paired_prediction_validation": {"paired_observed_targets_valid": True}},
        evidence_fingerprint=evidence_fingerprint, approval_status="approved" if approved else "pending_review",
        production_approved=approved, model_version=manifest["artifact_version"] if approved else None,
        artifact_path=manifest["artifact_path"] if approved else None,
        candidate_artifacts={"monthly_climatology": {"model_version": manifest["artifact_version"], "artifact_path": manifest["artifact_path"], "checksum_sha256": manifest["artifact_sha256"]}},
    )
    registry_path = tmp_path / "registry.json"
    RegistryManager(registry_path).save(WeatherModelRegistry(
        generated_at=datetime.now(timezone.utc), validation_report_path="validation.json", entries=[entry], production_approved=approved,
    ))
    return registry_path, manifest


def test_valid_live_forecast_is_used_inside_supported_horizon(tmp_path: Path) -> None:
    live = LiveWeatherResult(
        latitude=6.0, longitude=80.0, requested_date=date(2026, 1, 3), available=True,
        generated_at_utc=datetime.now(timezone.utc),
        forecast=LiveWeatherDay(date=date(2026, 1, 3), temperature_max_c=31.0, forecast_intervals=8), message="ok",
    )
    result = ForecastService(tmp_path / "missing.json", LiveClient(live)).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2026, 1, 3),
        reference_date=date(2026, 1, 1), latitude=6.0, longitude=80.0,
    )
    assert result.status == "available"
    assert result.source == "openweathermap"
    assert result.production_approved is False


def test_unapproved_artifact_is_never_used(tmp_path: Path) -> None:
    registry_path, _ = approved_registry(tmp_path, approved=False)
    result = ForecastService(registry_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2025, 1, 1), reference_date=date(2024, 12, 1),
    )
    assert result.status == "unavailable"
    assert "no_production_approved_model" in result.reliability.reason


def test_approved_verified_climatology_artifact_can_be_loaded(tmp_path: Path) -> None:
    registry_path, _ = approved_registry(tmp_path)
    result = ForecastService(registry_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2025, 1, 1), reference_date=date(2024, 12, 1),
    )
    assert result.status == "available"
    assert result.source == "approved_model"
    assert result.production_approved is True


def test_corrupt_or_invalidated_artifact_is_rejected(tmp_path: Path) -> None:
    registry_path, manifest = approved_registry(tmp_path)
    Path(manifest["artifact_path"]).write_bytes(b"corrupt")
    corrupt = ForecastService(registry_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2025, 1, 1), reference_date=date(2024, 12, 1),
    )
    assert corrupt.status == "unavailable"
    assert "artifact_integrity_failed" in corrupt.reliability.reason

    fresh_path, _ = approved_registry(tmp_path / "other", evidence_fingerprint="changed")
    invalidated = ForecastService(fresh_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2025, 1, 1), reference_date=date(2024, 12, 1),
    )
    assert invalidated.status == "unavailable"
    assert "artifact_evidence_invalidated" in invalidated.reliability.reason


def test_missing_manifest_and_outside_live_horizon_are_unavailable(tmp_path: Path) -> None:
    registry_path, manifest = approved_registry(tmp_path)
    Path(manifest["artifact_path"]).parent.joinpath("manifest.json").unlink()
    missing = ForecastService(registry_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2025, 1, 1), reference_date=date(2024, 12, 1),
    )
    assert missing.status == "unavailable"
    assert "artifact_manifest_missing" in missing.reliability.reason

    unapproved_path, _ = approved_registry(tmp_path / "unapproved", approved=False)
    outside = ForecastService(unapproved_path).get_forecast(
        district_id=78, target="temperature_max_c", forecast_date=date(2026, 1, 10), reference_date=date(2026, 1, 1), latitude=6.0, longitude=80.0,
    )
    assert outside.status == "unavailable"
    assert "requested_date_outside_live_provider_horizon" in outside.reliability.reason
