from datetime import date

from app.weather_model.monitoring.registry_audit import audit_model_run


def make_run(**overrides):
    run = {
        "run_id": "test_model_001",
        "district_id": 78,
        "target": "rainfall_mm",
        "model_name": "prophet",
        "training_start": date(2021, 1, 1),
        "training_cutoff": date(2025, 10, 1),
        "latest_calendar_month": date(2025, 10, 1),
        "latest_observed_month": date(2025, 10, 1),
        "latest_month_missing": False,
        "training_observations": 58,
        "forecast_horizon_months": 3,
        "validation_gate_passed": False,
        "production_approved": False,
        "status": "trained",
    }
    run.update(overrides)
    return run


def test_valid_model_integrity() -> None:
    result = audit_model_run(make_run(), forecast_count=3)
    assert result["integrity_passed"] is True
    assert result["issues"] == []
    assert result["warnings"] == []


def test_invalid_target_is_an_integrity_issue() -> None:
    result = audit_model_run(make_run(target="humidity"), forecast_count=3)
    assert "invalid_target" in result["issues"]


def test_insufficient_training_history_is_an_integrity_issue() -> None:
    result = audit_model_run(make_run(training_observations=23), forecast_count=3)
    assert "insufficient_training_observations" in result["issues"]


def test_forecast_count_must_match_declared_horizon() -> None:
    result = audit_model_run(make_run(), forecast_count=2)
    assert "forecast_count_mismatch" in result["issues"]


def test_approved_run_requires_validation_gate() -> None:
    result = audit_model_run(
        make_run(production_approved=True, validation_gate_passed=False), forecast_count=3
    )
    assert "approved_without_validation" in result["issues"]
    assert "approved_model_has_integrity_issues" in result["issues"]


def test_stale_or_missing_latest_observation_is_reported_as_warning() -> None:
    result = audit_model_run(
        make_run(
            latest_observed_month=date(2025, 8, 1),
            latest_month_missing=True,
        ),
        forecast_count=3,
    )
    assert result["observation_lag_months"] == 2
    assert set(result["warnings"]) == {
        "historical_observation_lag",
        "latest_month_missing",
    }
