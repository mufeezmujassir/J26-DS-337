"""Pure evaluation metrics for comparable monthly backtest predictions."""

from __future__ import annotations

import math
from statistics import mean


def calculate_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Actual and predicted arrays must be non-empty and have equal lengths")
    if not all(math.isfinite(value) for value in [*actual, *predicted]):
        raise ValueError("Metrics require finite values")
    errors = [prediction - observation for observation, prediction in zip(actual, predicted)]
    return {
        "mae": round(mean(abs(error) for error in errors), 4),
        "rmse": round(math.sqrt(mean(error**2 for error in errors)), 4),
        "bias": round(mean(errors), 4),
    }


def improvement_over_baseline(candidate_mae: float, baseline_mae: float) -> float | None:
    if baseline_mae <= 0:
        return None
    return round(100 * (baseline_mae - candidate_mae) / baseline_mae, 2)
