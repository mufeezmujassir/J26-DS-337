"""Pure, reproducible missing-aware preparation for temperature training data.

This module never queries or writes PostgreSQL.  It prepares only the history
available at a supplied rolling-origin date; test observations are never
imputed because they are the ground truth used for evaluation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class MonthlyObservation:
    month: date
    value: Optional[float]


@dataclass(frozen=True)
class TrainingPreparation:
    accepted: bool
    reason: str
    coverage_ratio: float
    expected_months: int
    observed_months: int
    imputed_months: tuple[str, ...]
    imputation_methods: tuple[tuple[str, str], ...]
    observations: tuple[tuple[date, float], ...]


def add_months(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _rejected(
    reason: str,
    *,
    coverage_ratio: float,
    expected_months: int,
    observed_months: int,
    imputed_months: tuple[str, ...] = (),
    imputation_methods: tuple[tuple[str, str], ...] = (),
) -> TrainingPreparation:
    return TrainingPreparation(
        accepted=False,
        reason=reason,
        coverage_ratio=coverage_ratio,
        expected_months=expected_months,
        observed_months=observed_months,
        imputed_months=imputed_months,
        imputation_methods=imputation_methods,
        observations=(),
    )


def prepare_training_history(
    observations: list[MonthlyObservation],
    origin: date,
    min_train_months: int = 36,
    min_coverage: float = 0.95,
) -> TrainingPreparation:
    """Prepare calendar-complete history known at ``origin`` only.

    The primary imputation method is an average of at least two *earlier*
    observations from the same calendar month.  The narrowly scoped fallback
    is linear interpolation from immediately adjacent observed months.  That
    fallback permits the early May 2022 Galle gap once April and June are both
    historical, while never looking beyond the origin.
    """
    if origin.day != 1:
        raise ValueError("Origin must be a month-start date")
    if min_train_months < 1:
        raise ValueError("min_train_months must be positive")
    if not 0 < min_coverage <= 1:
        raise ValueError("min_coverage must be in (0, 1]")

    historical = [item for item in observations if item.month <= origin]
    if not historical:
        return _rejected(
            "no_historical_observations",
            coverage_ratio=0.0,
            expected_months=0,
            observed_months=0,
        )
    if any(item.month.day != 1 for item in historical):
        raise ValueError("Observation months must be month-start dates")
    if len({item.month for item in historical}) != len(historical):
        raise ValueError("Duplicate observation months are not allowed")
    for item in historical:
        if item.value is not None and not math.isfinite(item.value):
            raise ValueError(f"Non-finite observation: {item.month}")

    first_month = min(item.month for item in historical)
    expected = [add_months(first_month, index) for index in range(
        (origin.year - first_month.year) * 12 + origin.month - first_month.month + 1
    )]
    values = {item.month: item.value for item in historical}
    observed_months = sum(values.get(month) is not None for month in expected)
    expected_months = len(expected)
    coverage_ratio = observed_months / expected_months
    if expected_months < min_train_months:
        return _rejected(
            "insufficient_training_months",
            coverage_ratio=coverage_ratio,
            expected_months=expected_months,
            observed_months=observed_months,
        )
    if coverage_ratio < min_coverage:
        return _rejected(
            "insufficient_coverage",
            coverage_ratio=coverage_ratio,
            expected_months=expected_months,
            observed_months=observed_months,
        )

    imputed: list[str] = []
    imputation_methods: list[tuple[str, str]] = []
    prepared: list[tuple[date, float]] = []
    for month in expected:
        value = values.get(month)
        if value is not None:
            prepared.append((month, float(value)))
            continue

        earlier_same_month = [
            float(candidate_value)
            for candidate_month, candidate_value in values.items()
            if candidate_value is not None
            and candidate_month < month
            and candidate_month.month == month.month
        ]
        if len(earlier_same_month) >= 2:
            value = sum(earlier_same_month) / len(earlier_same_month)
            method = "historical_same_calendar_month_mean"
        else:
            previous_month = add_months(month, -1)
            next_month = add_months(month, 1)
            previous_value = values.get(previous_month)
            next_value = values.get(next_month)
            if previous_value is None or next_value is None:
                return _rejected(
                    "unable_to_impute_month",
                    coverage_ratio=coverage_ratio,
                    expected_months=expected_months,
                    observed_months=observed_months,
                    imputed_months=tuple(imputed),
                    imputation_methods=tuple(imputation_methods),
                )
            # The dates are adjacent calendar months, so midpoint interpolation
            # is the appropriate deterministic time-based estimate.
            value = (float(previous_value) + float(next_value)) / 2
            method = "training_only_adjacent_linear_interpolation"
        imputed.append(month.isoformat())
        imputation_methods.append((month.isoformat(), method))
        prepared.append((month, float(value)))

    return TrainingPreparation(
        accepted=True,
        reason="accepted",
        coverage_ratio=coverage_ratio,
        expected_months=expected_months,
        observed_months=observed_months,
        imputed_months=tuple(imputed),
        imputation_methods=tuple(imputation_methods),
        observations=tuple(prepared),
    )
