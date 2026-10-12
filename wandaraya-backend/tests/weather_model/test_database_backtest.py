from datetime import date
from types import SimpleNamespace

from app.weather_model.backtesting.run_database_backtest import (
    compare_models,
    compare_prophet_predictions,
)


def prediction(model, month, actual, predicted):
    return SimpleNamespace(
        origin=date(2024, 12, 1),
        target_month=date(2025, month, 1),
        horizon=month,
        actual=actual,
        predicted=predicted,
        model_name=model,
    )


def test_fair_comparison_uses_common_pairs() -> None:
    models = {
        "monthly_climatology": SimpleNamespace(
            predictions=[
                prediction("monthly_climatology", 1, 100, 90),
                prediction("monthly_climatology", 2, 120, 110),
            ]
        ),
        "seasonal_naive": SimpleNamespace(
            predictions=[
                prediction("seasonal_naive", 1, 100, 95),
                prediction("seasonal_naive", 2, 120, 115),
            ]
        ),
        "prophet": SimpleNamespace(predictions=[prediction("prophet", 1, 100, 98)]),
    }
    report = compare_models(models)
    assert report["status"] == "completed"
    assert report["common_prediction_count"] == 1
    assert report["comparison"]["prophet"]["mae"] == 2.0
    assert report["comparison"]["seasonal_naive"]["mae"] == 5.0
    assert report["comparison"]["monthly_climatology"]["mae"] == 10.0


def test_no_common_predictions() -> None:
    models = {
        "monthly_climatology": SimpleNamespace(
            predictions=[prediction("monthly_climatology", 1, 100, 90)]
        ),
        "seasonal_naive": SimpleNamespace(
            predictions=[prediction("seasonal_naive", 2, 120, 115)]
        ),
        "prophet": SimpleNamespace(predictions=[]),
    }
    report = compare_models(models)
    assert report["status"] == "insufficient_common_predictions"


def test_batch_consistency_reports_numerical_difference() -> None:
    old = {
        "results": {
            "prophet": {
                "predictions": [
                    {
                        "origin": "2024-12-01",
                        "target_month": "2025-01-01",
                        "horizon": 1,
                        "predicted": 10.0,
                    }
                ]
            }
        }
    }
    current = {
        "prophet": SimpleNamespace(predictions=[prediction("prophet", 1, 100, 10.0)])
    }
    report = compare_prophet_predictions(old, current)
    assert report["status"] == "compared"
    assert report["within_tolerance"] is True
