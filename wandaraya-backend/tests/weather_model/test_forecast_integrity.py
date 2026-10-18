from datetime import date

from app.weather_model.monitoring.forecast_integrity import validate_forecast_run


REFERENCE_DATE = date(2026, 10, 11)


def make_run(**overrides):
    run = {
        "run_id": "test_run_001",
        "district_id": 78,
        "target": "rainfall_mm",
        "model_name": "seasonal_naive",
        "latest_calendar_month": date(2026, 9, 1),
        "latest_observed_month": date(2026, 9, 1),
        "latest_month_missing": False,
        "forecast_horizon_months": 3,
        "training_observations": 58,
        "validation_gate_passed": True,
        "production_approved": False,
        "parameters": {
            "quality_metrics": {
                "validation_mae": 50.0,
                "validation_rmse": 70.0,
                "validation_months": 24,
                "validation_folds": 2,
                "holdout_mae": 50.0,
                "holdout_rmse": 70.0,
                "holdout_months": 10,
                "baseline_holdout_mae": {},
            }
        },
    }
    run.update(overrides)
    return run


def make_forecasts():
    return [
        {
            "forecast_month": date(2026, month, 1),
            "predicted_value": 120.0,
            "lower_bound": 100.0,
            "upper_bound": 140.0,
            "raw_prediction": 120.0,
        }
        for month in (10, 11, 12)
    ]


def validate(run=None, forecasts=None):
    return validate_forecast_run(
        run or make_run(),
        forecasts if forecasts is not None else make_forecasts(),
        reference_date=REFERENCE_DATE,
    )


def test_valid_current_forecast_run_is_ready_for_preliminary_review() -> None:
    result = validate()
    assert result["integrity_passed"] is True
    assert result["production_ready_for_review"] is True


def test_duplicate_forecast_month_fails_integrity() -> None:
    forecasts = make_forecasts()
    forecasts[-1]["forecast_month"] = date(2026, 11, 1)
    result = validate(forecasts=forecasts)
    assert "duplicate_forecast_month" in result["issues"]
    assert "missing_forecast_month" in result["issues"]


def test_missing_forecast_month_fails_integrity() -> None:
    result = validate(forecasts=make_forecasts()[:2])
    assert "missing_forecast_month" in result["issues"]
    assert "forecast_count_mismatch" in result["issues"]


def test_non_finite_prediction_fails_integrity() -> None:
    forecasts = make_forecasts()
    forecasts[0]["predicted_value"] = float("nan")
    result = validate(forecasts=forecasts)
    assert "non_finite_predicted_value" in result["issues"]


def test_invalid_uncertainty_interval_fails_integrity() -> None:
    forecasts = make_forecasts()
    forecasts[0]["lower_bound"] = 130.0
    result = validate(forecasts=forecasts)
    assert "invalid_prediction_interval" in result["issues"]


def test_negative_rainfall_fails_integrity() -> None:
    forecasts = make_forecasts()
    forecasts[0]["predicted_value"] = -1.0
    result = validate(forecasts=forecasts)
    assert "negative_rainfall_prediction" in result["issues"]


def test_expired_forecast_and_stale_observations_block_review_only() -> None:
    result = validate(
        run=make_run(
            latest_calendar_month=date(2025, 10, 1),
            latest_observed_month=date(2025, 10, 1),
        ),
        forecasts=[
            {
                "forecast_month": date(2025, month, 1),
                "predicted_value": 120.0,
                "lower_bound": 100.0,
                "upper_bound": 140.0,
                "raw_prediction": 120.0,
            }
            for month in (11, 12)
        ] + [
            {
                "forecast_month": date(2026, 1, 1),
                "predicted_value": 120.0,
                "lower_bound": 100.0,
                "upper_bound": 140.0,
                "raw_prediction": 120.0,
            }
        ],
    )
    assert result["integrity_passed"] is True
    assert result["production_ready_for_review"] is False
    assert set(result["readiness_blockers"]) >= {
        "stale_training_observations",
        "forecast_horizon_expired",
    }


def test_missing_quality_evidence_blocks_review() -> None:
    result = validate(run=make_run(parameters={}))
    assert result["integrity_passed"] is True
    assert result["quality_eligible_for_review"] is False
    assert "quality_gate_not_passed" in result["readiness_blockers"]
