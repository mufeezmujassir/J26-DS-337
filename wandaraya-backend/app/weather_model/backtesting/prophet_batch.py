"""Batch Prophet forecasts for one leakage-safe rolling-origin fold."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from app.weather_model.backtesting.schemas import MonthlyObservation


VALID_TARGETS = {"rainfall_mm", "temperature_min_c", "temperature_max_c"}


def predict_prophet_batch(
    train: list[MonthlyObservation],
    target_months: list[date],
    target: str,
) -> dict[date, float]:
    """Fit exactly once, then return all requested future monthly predictions."""
    if target not in VALID_TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    if not train:
        raise ValueError("Training data is empty")
    if not target_months:
        raise ValueError("No forecast months requested")
    latest_training_month = max(row.month for row in train)
    if any(month <= latest_training_month for month in target_months):
        raise ValueError("Forecast months must follow training data")

    from prophet import Prophet

    frame = pd.DataFrame({"ds": [row.month for row in train], "y": [row.value for row in train]})
    model = Prophet(
        growth="linear",
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=1.0,
        interval_width=0.80,
    )
    model.add_seasonality(
        name="yearly_monthly", period=365.25, fourier_order=3, prior_scale=1.0
    )
    model.fit(frame)
    forecast = model.predict(pd.DataFrame({"ds": target_months}))
    predictions: dict[date, float] = {}
    for _, row in forecast.iterrows():
        month = row["ds"].date()
        value = float(row["yhat"])
        if not math.isfinite(value):
            raise ValueError("Non-finite Prophet prediction")
        if target == "rainfall_mm":
            value = max(0.0, value)
        elif not 0.0 <= value <= 45.0:
            raise ValueError("Temperature prediction is outside the accepted range")
        predictions[month] = value
    if set(predictions) != set(target_months):
        raise ValueError("Prophet did not return every requested forecast month")
    return predictions


class ProphetBatchPredictor:
    """Adapter exposing the rolling-origin engine's optional batch interface."""

    def __init__(self, target: str) -> None:
        self.target = target

    def predict_batch(
        self,
        train: list[MonthlyObservation],
        target_months: list[date],
    ) -> dict[date, float]:
        return predict_prophet_batch(train, target_months, self.target)
