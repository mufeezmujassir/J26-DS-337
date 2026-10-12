"""Run PostgreSQL-backed, non-production Prophet and baseline backtesting."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from app.weather_model.backtesting.baselines import (
    monthly_climatology_predict,
    seasonal_naive_predict,
)
from app.weather_model.backtesting.metrics import calculate_metrics, improvement_over_baseline
from app.weather_model.backtesting.observation_loader import (
    ALLOWED_TARGETS,
    load_monthly_observations,
)
from app.weather_model.backtesting.prophet_batch import ProphetBatchPredictor
from app.weather_model.backtesting.rolling_origin import rolling_origin_comparison
from app.weather_model.persistence.database import get_weather_engine


def prediction_key(prediction: Any) -> tuple[date, date, int]:
    return prediction.origin, prediction.target_month, prediction.horizon


def compare_models(results: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate metrics on only origin-month pairs shared by every model."""
    if not results:
        return {"status": "no_models", "comparison": {}}

    keyed: dict[str, dict[tuple[date, date, int], Any]] = {}
    for name, result in results.items():
        values = {}
        for prediction in result.predictions:
            key = prediction_key(prediction)
            if key in values:
                raise ValueError(f"Duplicate prediction pair for {name}: {key}")
            values[key] = prediction
        keyed[name] = values

    common_keys = set.intersection(*(set(values) for values in keyed.values()))
    if not common_keys:
        return {
            "status": "insufficient_common_predictions",
            "common_prediction_count": 0,
            "comparison": {},
        }

    comparison: dict[str, dict[str, Any]] = {}
    ordered_keys = sorted(common_keys)
    for name, values in keyed.items():
        predictions = [values[key] for key in ordered_keys]
        actual = [float(item.actual) for item in predictions]
        predicted = [float(item.predicted) for item in predictions]
        horizons: dict[str, dict[str, float]] = {}
        for horizon in sorted({item.horizon for item in predictions}):
            horizon_items = [item for item in predictions if item.horizon == horizon]
            horizons[str(horizon)] = calculate_metrics(
                [float(item.actual) for item in horizon_items],
                [float(item.predicted) for item in horizon_items],
            )
        comparison[name] = {
            **calculate_metrics(actual, predicted),
            "prediction_count": len(predictions),
            "metrics_by_horizon": horizons,
        }

    for name, metrics in comparison.items():
        for baseline in ("monthly_climatology", "seasonal_naive"):
            baseline_metrics = comparison.get(baseline)
            metrics[f"improvement_over_{baseline}_percent"] = (
                improvement_over_baseline(metrics["mae"], baseline_metrics["mae"])
                if baseline_metrics
                else None
            )
    return {
        "status": "completed",
        "common_prediction_count": len(ordered_keys),
        "comparison": comparison,
    }


def compare_prophet_predictions(previous_report: Mapping[str, Any], results: Mapping[str, Any]) -> dict[str, Any]:
    """Record, rather than hide, any batch-vs-prior Prophet prediction drift."""
    previous = previous_report.get("results", {}).get("prophet", {}).get("predictions", [])
    current_result = results.get("prophet")
    if not previous or current_result is None:
        return {"status": "no_prior_prophet_report"}
    old = {
        (item["origin"], item["target_month"], item["horizon"]): float(item["predicted"])
        for item in previous
    }
    new = {
        (item.origin.isoformat(), item.target_month.isoformat(), item.horizon): float(item.predicted)
        for item in current_result.predictions
    }
    common = sorted(set(old) & set(new))
    if not common:
        return {"status": "no_common_prior_predictions"}
    differences = [abs(old[key] - new[key]) for key in common]
    tolerance = 1e-6
    return {
        "status": "compared",
        "common_prediction_count": len(common),
        "max_absolute_difference": max(differences),
        "mean_absolute_difference": sum(differences) / len(differences),
        "within_tolerance": max(differences) <= tolerance,
        "tolerance": tolerance,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-id", required=True, type=int)
    parser.add_argument("--target", required=True, choices=sorted(ALLOWED_TARGETS))
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--min-train-months", type=int, default=36)
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument(
        "--strict-training",
        action="store_true",
        help="Disable missing-aware temperature preparation for a complete-case comparison.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/weather/reports/backtesting")
    )
    arguments = parser.parse_args()

    engine = get_weather_engine()
    try:
        observations = load_monthly_observations(
            engine, arguments.district_id, arguments.target, arguments.cutoff
        )
    finally:
        engine.dispose()
    if not observations:
        raise ValueError("No valid observations exist for this district and target")

    predictors = {
        "monthly_climatology": monthly_climatology_predict,
        "seasonal_naive": seasonal_naive_predict,
        "prophet": ProphetBatchPredictor(arguments.target),
    }
    missing_aware_training = (
        arguments.target in {"temperature_min_c", "temperature_max_c"}
        and not arguments.strict_training
    )
    results = rolling_origin_comparison(
        observations,
        target=arguments.target,
        predictors=predictors,
        horizon_months=arguments.horizon,
        min_training_months=arguments.min_train_months,
        step_months=arguments.step_months,
        missing_aware_training=missing_aware_training,
        min_training_coverage=0.95,
    )
    comparison = compare_models(results)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = arguments.output_dir / (
        f"district_{arguments.district_id}_{arguments.target}_backtest.json"
    )
    previous_report = None
    if output_path.exists():
        try:
            previous_report = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_report = None
    payload = {
        "district_id": arguments.district_id,
        "target": arguments.target,
        "cutoff": arguments.cutoff,
        "observation_count": len(observations),
        "first_observation_month": observations[0].month,
        "last_observation_month": observations[-1].month,
        "horizon_months": arguments.horizon,
        "min_train_months": arguments.min_train_months,
        "step_months": arguments.step_months,
        "training_policy": {
            "name": (
                "missing_aware_training_only"
                if missing_aware_training
                else "strict_complete_case"
            ),
            "min_coverage": 0.95 if missing_aware_training else None,
            "test_actuals_imputed": False,
        },
        "results": {name: result.to_dict() for name, result in results.items()},
        "fair_comparison": comparison,
        "batch_prediction_consistency": (
            compare_prophet_predictions(previous_report, results)
            if previous_report is not None
            else {"status": "no_prior_report"}
        ),
        "selected_model": "pending_evaluation",
        "production_approved": False,
    }
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"District: {arguments.district_id}")
    print(f"Target: {arguments.target}")
    print(f"Observed months: {len(observations)} ({observations[0].month} to {observations[-1].month})\n")
    print(f"{'Model':<24} {'Folds':>5} {'MAE':>10} {'RMSE':>10}")
    print("-" * 55)
    for name, result in results.items():
        metrics = comparison.get("comparison", {}).get(name, {})
        print(
            f"{name:<24} {result.fold_count:>5} "
            f"{str(metrics.get('mae', 'n/a')):>10} "
            f"{str(metrics.get('rmse', 'n/a')):>10}"
        )
    print("\nSelected model: Pending evaluation")
    print("Production approved: No")
    print("Report:", output_path)


if __name__ == "__main__":
    main()
