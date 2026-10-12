"""Strict rolling-origin backtesting for comparable monthly forecast models."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import date

from app.weather_model.backtesting.metrics import calculate_metrics, improvement_over_baseline
from app.weather_model.backtesting.missing_aware import (
    MonthlyObservation as MissingAwareObservation,
    prepare_training_history,
)
from app.weather_model.backtesting.schemas import (
    BacktestPrediction,
    BacktestResult,
    MonthlyObservation,
)


Predictor = Callable[[list[MonthlyObservation], date], float]


def _predict_fold(
    predictor: Predictor,
    train: list[MonthlyObservation],
    test: list[MonthlyObservation],
) -> list[float]:
    """Use batch-capable predictors once per origin; preserve simple callables."""
    target_months = [item.month for item in test]
    batch_predict = getattr(predictor, "predict_batch", None)
    if callable(batch_predict):
        returned = batch_predict(train, target_months)
        return [float(returned[month]) for month in target_months]
    return [float(predictor(train, month)) for month in target_months]


def add_months(value: date, count: int) -> date:
    index = value.year * 12 + value.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    """Return inclusive first-of-month values from ``start`` through ``end``."""
    count = (end.year - start.year) * 12 + end.month - start.month
    return [add_months(start, offset) for offset in range(count + 1)]


def _validate_observations(observations: list[MonthlyObservation]) -> list[MonthlyObservation]:
    ordered = sorted(observations, key=lambda item: item.month)
    if not ordered:
        raise ValueError("At least one observation is required")
    if any(item.month.day != 1 for item in ordered):
        raise ValueError("Observations must use the first day of each month")
    # Missing values are retained so folds can report whether the gap was in
    # training or evaluation. Strict mode later skips affected training folds;
    # missing-aware mode may prepare eligible temperature training folds.
    if any(item.value is not None and not math.isfinite(item.value) for item in ordered):
        raise ValueError("Observations must be finite")
    if len({item.month for item in ordered}) != len(ordered):
        raise ValueError("Duplicate observation months are not allowed")
    return ordered


def _folds(
    observations: list[MonthlyObservation],
    *,
    horizon_months: int,
    min_training_months: int,
    step_months: int,
    missing_aware_training: bool,
    min_training_coverage: float,
):
    """Yield calendar-aligned folds without changing historical observations.

    ``observations`` has one item per database row, so an absent row is not
    represented in the input list.  Each training history is rebuilt over its
    complete calendar range with ``None`` for such months.  The existing
    missing-aware policy can then make a documented, training-only decision
    for temperature, while strict rainfall folds remain ineligible.
    """
    actual_by_month = {item.month: item for item in observations}
    first_month = observations[0].month
    last_record_month = observations[-1].month
    origin = add_months(first_month, min_training_months - 1)
    last_eligible_origin = add_months(last_record_month, -horizon_months)

    # Origins advance in calendar months, rather than positions in a list
    # whose length may be shortened by an absent database row.  The bound
    # avoids scheduling test windows beyond the known historical timeline.
    while origin <= last_eligible_origin:
        train = [
            actual_by_month.get(month, MonthlyObservation(month=month, value=None))
            for month in month_range(first_month, origin)
        ]
        target_months = [add_months(origin, offset) for offset in range(1, horizon_months + 1)]
        missing_test_months = [
            month for month in target_months
            if month not in actual_by_month or actual_by_month[month].value is None
        ]
        if missing_test_months:
            yield origin, None, None, "missing_test_actual", {
                "missing_test_months": [month.isoformat() for month in missing_test_months],
            }
            origin = add_months(origin, step_months)
            continue
        if missing_aware_training:
            preparation = prepare_training_history(
                [MissingAwareObservation(month=item.month, value=item.value) for item in train],
                origin=origin,
                min_train_months=min_training_months,
                min_coverage=min_training_coverage,
            )
            if not preparation.accepted:
                yield origin, None, None, preparation.reason, {
                    "training_coverage_ratio": preparation.coverage_ratio,
                    "imputed_months": list(preparation.imputed_months),
                    "imputation_methods": dict(preparation.imputation_methods),
                }
                origin = add_months(origin, step_months)
                continue
            prepared_train = [
                MonthlyObservation(month=month, value=value)
                for month, value in preparation.observations
            ]
            metadata = {
                "origin": origin.isoformat(),
                "training_coverage_ratio": preparation.coverage_ratio,
                "imputed_months": list(preparation.imputed_months),
                "imputation_methods": dict(preparation.imputation_methods),
                "imputation_policy": "training_only_missing_aware",
            }
        else:
            if any(item.value is None for item in train):
                yield origin, None, None, "incomplete_training_history", {}
                origin = add_months(origin, step_months)
                continue
            prepared_train = train
            metadata = {
                "origin": origin.isoformat(),
                "training_coverage_ratio": 1.0,
                "imputed_months": [],
                "imputation_methods": {},
                "imputation_policy": "strict_complete_case",
            }
        yield origin, prepared_train, [actual_by_month[month] for month in target_months], None, metadata
        origin = add_months(origin, step_months)


def rolling_origin_backtest(
    observations: list[MonthlyObservation],
    *,
    target: str,
    model_name: str,
    predictor: Predictor,
    horizon_months: int = 3,
    min_training_months: int = 24,
    step_months: int = 3,
    missing_aware_training: bool = False,
    min_training_coverage: float = 0.95,
) -> BacktestResult:
    """Evaluate one predictor at repeated origins, retaining skip diagnostics."""
    if horizon_months < 1 or min_training_months < 1 or step_months < 1:
        raise ValueError("Horizon, minimum training history, and step must be positive")
    ordered = _validate_observations(observations)
    predictions: list[BacktestPrediction] = []
    skipped: list[dict[str, str]] = []
    fold_metadata: list[dict] = []
    fold_count = 0
    for origin, train, test, reason, detail in _folds(
        ordered,
        horizon_months=horizon_months,
        min_training_months=min_training_months,
        step_months=step_months,
        missing_aware_training=missing_aware_training,
        min_training_coverage=min_training_coverage,
    ):
        if reason:
            skipped.append({"origin": origin.isoformat(), "reason": reason, **detail})
            continue
        try:
            fold_predictions = _predict_fold(predictor, train, test)
            if not all(math.isfinite(value) for value in fold_predictions):
                raise ValueError("non_finite_prediction")
        except Exception as exc:
            skipped.append({"origin": origin.isoformat(), "reason": f"predictor_failed: {exc}"})
            continue
        fold_count += 1
        fold_metadata.append(detail)
        predictions.extend(
            BacktestPrediction(
                origin=origin,
                target_month=item.month,
                horizon=horizon,
                actual=item.value,
                predicted=value,
                model_name=model_name,
            )
            for horizon, (item, value) in enumerate(zip(test, fold_predictions), start=1)
        )
    metrics = (
        calculate_metrics([item.actual for item in predictions], [item.predicted for item in predictions])
        if predictions
        else {}
    )
    return BacktestResult(
        model_name=model_name,
        target=target,
        observation_count=len(ordered),
        fold_count=fold_count,
        prediction_count=len(predictions),
        metrics=metrics,
        predictions=predictions,
        skipped_folds=skipped,
        fold_metadata=fold_metadata,
    )


def rolling_origin_comparison(
    observations: list[MonthlyObservation],
    *,
    target: str,
    predictors: Mapping[str, Predictor],
    horizon_months: int = 3,
    min_training_months: int = 24,
    step_months: int = 3,
    missing_aware_training: bool = False,
    min_training_coverage: float = 0.95,
) -> dict[str, BacktestResult]:
    """Evaluate models on exactly the same successful origin-target pairs.

    If one candidate cannot predict a fold, the fold is skipped for *every*
    model, preventing easier folds from biasing the comparison.
    """
    if not predictors:
        raise ValueError("At least one predictor is required")
    ordered = _validate_observations(observations)
    shared_predictions: dict[str, list[BacktestPrediction]] = {name: [] for name in predictors}
    skipped: list[dict[str, str]] = []
    fold_metadata: list[dict] = []
    fold_count = 0
    for origin, train, test, reason, detail in _folds(
        ordered,
        horizon_months=horizon_months,
        min_training_months=min_training_months,
        step_months=step_months,
        missing_aware_training=missing_aware_training,
        min_training_coverage=min_training_coverage,
    ):
        if reason:
            skipped.append({"origin": origin.isoformat(), "reason": reason, **detail})
            continue
        per_model: dict[str, list[float]] = {}
        try:
            for name, predictor in predictors.items():
                values = _predict_fold(predictor, train, test)
                if not all(math.isfinite(value) for value in values):
                    raise ValueError(f"{name}: non_finite_prediction")
                per_model[name] = values
        except Exception as exc:
            skipped.append({"origin": origin.isoformat(), "reason": f"predictor_failed: {exc}"})
            continue
        fold_count += 1
        fold_metadata.append(detail)
        for name, values in per_model.items():
            shared_predictions[name].extend(
                BacktestPrediction(
                    origin=origin,
                    target_month=item.month,
                    horizon=horizon,
                    actual=item.value,
                    predicted=value,
                    model_name=name,
                )
                for horizon, (item, value) in enumerate(zip(test, values), start=1)
            )

    results: dict[str, BacktestResult] = {}
    for name, predictions in shared_predictions.items():
        metrics = (
            calculate_metrics([item.actual for item in predictions], [item.predicted for item in predictions])
            if predictions
            else {}
        )
        results[name] = BacktestResult(
            model_name=name,
            target=target,
            observation_count=len(ordered),
            fold_count=fold_count,
            prediction_count=len(predictions),
            metrics=metrics,
            predictions=predictions,
            skipped_folds=list(skipped),
            fold_metadata=list(fold_metadata),
        )

    baseline_maes = [
        result.metrics.get("mae")
        for name, result in results.items()
        if name in {"monthly_climatology", "seasonal_naive"} and result.metrics
    ]
    if baseline_maes:
        best_baseline_mae = min(baseline_maes)
        for result in results.values():
            if result.metrics:
                result.metrics["improvement_over_best_baseline_percent"] = improvement_over_baseline(
                    result.metrics["mae"], best_baseline_mae
                )
    return results
