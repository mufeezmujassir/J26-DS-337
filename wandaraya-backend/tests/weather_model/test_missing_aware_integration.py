from datetime import date

from app.weather_model.backtesting.baselines import (
    monthly_climatology_predict,
    seasonal_naive_predict,
)
from app.weather_model.backtesting.rolling_origin import (
    add_months,
    rolling_origin_comparison,
)
from app.weather_model.backtesting.schemas import MonthlyObservation


class CountingBatchPredictor:
    def __init__(self):
        self.training_end_months = []

    def predict_batch(self, train, target_months):
        self.training_end_months.append(max(item.month for item in train))
        return {month: 24.0 for month in target_months}


def make_temperature_history(*, missing_months=()):
    start = date(2021, 1, 1)
    return [
        MonthlyObservation(
            month=add_months(start, index),
            value=None if add_months(start, index) in missing_months else 20.0 + index * 0.05,
        )
        for index in range(58)
    ]


def run_missing_aware(history, predictor=None):
    predictor = predictor or CountingBatchPredictor()
    results = rolling_origin_comparison(
        history,
        target="temperature_min_c",
        predictors={
            "monthly_climatology": monthly_climatology_predict,
            "seasonal_naive": seasonal_naive_predict,
            "prophet": predictor,
        },
        min_training_months=36,
        horizon_months=3,
        step_months=3,
        missing_aware_training=True,
    )
    return results, predictor


def test_missing_may_in_training_produces_accepted_temperature_folds() -> None:
    results, _ = run_missing_aware(
        make_temperature_history(missing_months=(date(2022, 5, 1),))
    )
    result = results["prophet"]
    assert result.fold_count > 0
    assert any("2022-05-01" in item["imputed_months"] for item in result.fold_metadata)


def test_missing_evaluation_actual_is_skipped_not_imputed() -> None:
    results, _ = run_missing_aware(
        make_temperature_history(missing_months=(date(2024, 1, 1),))
    )
    result = results["prophet"]
    assert any(item["reason"] == "missing_test_actual" for item in result.skipped_folds)
    assert all(item.target_month != date(2024, 1, 1) for item in result.predictions)


def test_future_observations_are_not_used_by_batch_predictor() -> None:
    results, predictor = run_missing_aware(
        make_temperature_history(missing_months=(date(2022, 5, 1),))
    )
    origins = [item["origin"] for item in results["prophet"].fold_metadata]
    assert [item.isoformat() for item in predictor.training_end_months] == origins


def test_every_model_uses_identical_origin_target_pairs() -> None:
    results, _ = run_missing_aware(
        make_temperature_history(missing_months=(date(2022, 5, 1),))
    )
    pairs = {
        name: [(item.origin, item.target_month, item.horizon) for item in result.predictions]
        for name, result in results.items()
    }
    assert pairs["monthly_climatology"] == pairs["seasonal_naive"] == pairs["prophet"]


def test_complete_rainfall_history_remains_strict_without_imputations() -> None:
    history = [
        MonthlyObservation(month=add_months(date(2021, 1, 1), index), value=100.0 + index)
        for index in range(58)
    ]
    results = rolling_origin_comparison(
        history,
        target="rainfall_mm",
        predictors={"seasonal_naive": seasonal_naive_predict},
        min_training_months=36,
        horizon_months=3,
        step_months=3,
    )
    assert results["seasonal_naive"].fold_count > 0
    assert all(item["imputed_months"] == [] for item in results["seasonal_naive"].fold_metadata)


def test_strict_rainfall_with_missing_value_skips_folds_without_crashing() -> None:
    history = [
        MonthlyObservation(
            month=add_months(date(2021, 1, 1), index),
            value=None if index == 20 else 100.0 + index,
        )
        for index in range(58)
    ]
    results = rolling_origin_comparison(
        history,
        target="rainfall_mm",
        predictors={"seasonal_naive": seasonal_naive_predict},
        min_training_months=36,
        horizon_months=3,
        step_months=3,
    )
    result = results["seasonal_naive"]
    assert result.fold_count == 0
    assert any(item["reason"] == "incomplete_training_history" for item in result.skipped_folds)
    assert result.fold_metadata == []


def test_low_training_coverage_is_recorded_as_explicit_skip() -> None:
    history = make_temperature_history(
        missing_months=(date(2022, 5, 1), date(2022, 6, 1), date(2022, 7, 1))
    )
    results, _ = run_missing_aware(history)
    assert any(item["reason"] == "insufficient_coverage" for item in results["prophet"].skipped_folds)


def test_fold_metadata_records_training_only_policy() -> None:
    results, _ = run_missing_aware(
        make_temperature_history(missing_months=(date(2022, 5, 1),))
    )
    metadata = results["prophet"].fold_metadata[0]
    assert metadata["imputation_policy"] == "training_only_missing_aware"
    assert metadata["training_coverage_ratio"] >= 0.95
