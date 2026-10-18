from app.weather_model.backtesting.model_selection_validation import (
    validate_paired_predictions,
    validate_series,
)


def prediction(model: str, predicted: float, actual: float = 10.0) -> dict:
    return {
        "model_name": model,
        "origin": "2024-01-01",
        "target_month": "2024-02-01",
        "horizon": 1,
        "actual": actual,
        "predicted": predicted,
    }


def detailed_report(actual: float = 10.0) -> dict:
    return {
        "results": {
            model: {"predictions": [prediction(model, value, actual)]}
            for model, value in (
                ("monthly_climatology", 10.5),
                ("seasonal_naive", 10.6),
                ("prophet", 10.2),
            )
        }
    }


def evidence() -> dict:
    horizon_metrics = {
        str(horizon): {"mae": 1.0, "rmse": 1.0, "bias": 0.1}
        for horizon in (1, 2, 3)
    }
    return {
        "district_id": 78,
        "target": "temperature_min_c",
        "independent_rolling_origin_folds": 5,
        "training_policy": {"name": "missing_aware_training_only"},
        "imputed_training_folds": 1,
        "model_metrics": {
            "monthly_climatology": {
                "mae": 1.0,
                "rmse": 1.1,
                "bias": 0.1,
                "metrics_by_horizon": horizon_metrics,
            },
            "seasonal_naive": {
                "mae": 1.2,
                "rmse": 1.3,
                "bias": 0.1,
                "metrics_by_horizon": horizon_metrics,
            },
            "prophet": {
                "mae": 0.9,
                "rmse": 1.0,
                "bias": 0.1,
                "metrics_by_horizon": horizon_metrics,
            },
        },
    }


def test_paired_validation_requires_same_keys_and_actuals() -> None:
    validated = validate_paired_predictions(detailed_report())
    assert validated["paired_observed_targets_valid"] is True

    invalid = detailed_report()
    invalid["results"]["prophet"]["predictions"][0]["actual"] = 11.0
    assert validate_paired_predictions(invalid)["paired_observed_targets_valid"] is False


def test_clear_prophet_improvement_is_candidate_not_approval() -> None:
    result = validate_series(evidence(), detailed_report())
    assert result["evidence_status"] == "eligible_for_review"
    assert result["provisional_candidate"] == "prophet"
    assert result["recommendation"] == "prophet_candidate"
    assert result["production_approved"] is False


def test_no_predictions_is_explicitly_insufficient_evidence() -> None:
    empty_evidence = evidence()
    empty_evidence["independent_rolling_origin_folds"] = 0
    for model in empty_evidence["model_metrics"].values():
        model["mae"] = None
    empty = {"results": {model: {"predictions": []} for model in empty_evidence["model_metrics"]}}

    result = validate_series(empty_evidence, empty)
    assert result["evidence_status"] == "insufficient_evidence"
    assert result["recommendation"] == "insufficient_evidence"
