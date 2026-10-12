"""Transparent baseline predictors used for fair rolling-origin comparisons."""

from __future__ import annotations

from statistics import mean

from app.weather_model.backtesting.schemas import MonthlyObservation


def monthly_climatology_predict(
    train: list[MonthlyObservation],
    target_month,
) -> float:
    values = [item.value for item in train if item.month.month == target_month.month]
    if not values:
        raise ValueError("No historical observations for target month")
    return float(mean(values))


def seasonal_naive_predict(
    train: list[MonthlyObservation],
    target_month,
) -> float:
    observations = {item.month: item.value for item in train}
    try:
        previous_year = target_month.replace(year=target_month.year - 1)
    except ValueError as exc:
        raise ValueError("Target month must be a valid calendar month") from exc
    if previous_year not in observations:
        raise ValueError("Previous-year observation unavailable")
    return float(observations[previous_year])
