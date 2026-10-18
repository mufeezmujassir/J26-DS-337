"""Leakage-safe Prophet predictor for rolling-origin monthly experiments."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from app.weather_model.backtesting.schemas import MonthlyObservation


class ProphetMonthlyPredictor:
    """Fit Prophet once per distinct historical origin and predict requested months.

    The cache key includes every training observation, so a model never crosses
    origins and cannot use future observations.  It simply avoids fitting the
    same origin three times for a 3-month test window.
    """

    def __init__(
        self,
        target: str,
        *,
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 1.0,
        yearly_fourier_order: int = 3,
    ) -> None:
        if target not in {"rainfall_mm", "temperature_min_c", "temperature_max_c"}:
            raise ValueError(f"Unsupported target: {target}")
        self.target = target
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_prior_scale = seasonality_prior_scale
        self.yearly_fourier_order = yearly_fourier_order
        self._training_key: tuple[tuple[date, float], ...] | None = None
        self._model = None

    def _fit(self, train: list[MonthlyObservation]) -> None:
        if len(train) < 2:
            raise ValueError("Prophet requires at least two observations")
        key = tuple((item.month, float(item.value)) for item in train)
        if key == self._training_key:
            return

        # Local import keeps baseline-only experiments lightweight.
        from prophet import Prophet

        frame = pd.DataFrame({"ds": [item.month for item in train], "y": [item.value for item in train]})
        model = Prophet(
            growth="linear",
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_prior_scale=self.seasonality_prior_scale,
            interval_width=0.80,
        )
        model.add_seasonality(
            name="yearly_monthly",
            period=365.25,
            fourier_order=self.yearly_fourier_order,
            prior_scale=self.seasonality_prior_scale,
        )
        model.fit(frame)
        self._training_key = key
        self._model = model

    def __call__(self, train: list[MonthlyObservation], target_month: date) -> float:
        self._fit(train)
        forecast = self._model.predict(pd.DataFrame({"ds": [target_month]}))
        prediction = float(forecast.iloc[0]["yhat"])
        if not math.isfinite(prediction):
            raise ValueError("Prophet returned non-finite prediction")
        if self.target == "rainfall_mm":
            return max(0.0, prediction)
        if not 0.0 <= prediction <= 45.0:
            raise ValueError("Temperature prediction is outside the accepted range")
        return prediction
