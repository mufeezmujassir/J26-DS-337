from datetime import date

import pytest

from app.weather_model.backtesting.baselines import (
    monthly_climatology_predict,
    seasonal_naive_predict,
)
from app.weather_model.backtesting.metrics import calculate_metrics, improvement_over_baseline
from app.weather_model.backtesting.rolling_origin import (
    add_months,
    rolling_origin_backtest,
    rolling_origin_comparison,
)
from app.weather_model.backtesting.schemas import MonthlyObservation


def make_observations(count=60):
    start = date(2021, 1, 1)
    return [
        MonthlyObservation(
            month=add_months(start, index),
            value=float(100 + (index % 12) * 5),
        )
        for index in range(count)
    ]


def test_add_months_handles_year_boundary() -> None:
    assert add_months(date(2024, 12, 1), 1) == date(2025, 1, 1)


def test_monthly_climatology_uses_only_past_same_month_observations() -> None:
    train = [
        MonthlyObservation(date(2021, 1, 1), 10.0),
        MonthlyObservation(date(2022, 1, 1), 30.0),
    ]
    assert monthly_climatology_predict(train, date(2023, 1, 1)) == 20.0


def test_seasonal_naive_requires_previous_year_observation() -> None:
    with pytest.raises(ValueError, match="Previous-year"):
        seasonal_naive_predict([], date(2024, 1, 1))


def test_metrics_and_baseline_improvement_are_calculated() -> None:
    assert calculate_metrics([10.0, 20.0], [12.0, 18.0]) == {
        "mae": 2.0,
        "rmse": 2.0,
        "bias": 0.0,
    }
    assert improvement_over_baseline(8.0, 10.0) == 20.0


def test_rolling_origin_produces_only_unseen_future_predictions() -> None:
    result = rolling_origin_backtest(
        make_observations(),
        target="rainfall_mm",
        model_name="seasonal_naive",
        predictor=seasonal_naive_predict,
    )
    assert result.fold_count > 0
    assert result.prediction_count == result.fold_count * 3
    assert all(item.target_month > item.origin for item in result.predictions)


def test_missing_month_records_skipped_fold_diagnostic() -> None:
    observations = make_observations()
    observations.pop(25)
    result = rolling_origin_backtest(
        observations,
        target="rainfall_mm",
        model_name="monthly_climatology",
        predictor=monthly_climatology_predict,
    )
    assert any(item["reason"] == "incomplete_training_history" for item in result.skipped_folds)


def test_comparison_uses_identical_prediction_pairs_for_every_model() -> None:
    results = rolling_origin_comparison(
        make_observations(),
        target="rainfall_mm",
        predictors={
            "monthly_climatology": monthly_climatology_predict,
            "seasonal_naive": seasonal_naive_predict,
        },
    )
    left = [(item.origin, item.target_month) for item in results["monthly_climatology"].predictions]
    right = [(item.origin, item.target_month) for item in results["seasonal_naive"].predictions]
    assert left == right
    assert results["monthly_climatology"].fold_count == results["seasonal_naive"].fold_count


def test_batch_predictor_is_called_once_per_successful_fold() -> None:
    class CountingBatchPredictor:
        def __init__(self):
            self.calls = 0

        def predict_batch(self, train, target_months):
            self.calls += 1
            return {month: 100.0 for month in target_months}

    predictor = CountingBatchPredictor()
    result = rolling_origin_backtest(
        make_observations(),
        target="rainfall_mm",
        model_name="batch_test",
        predictor=predictor,
    )
    assert predictor.calls == result.fold_count
