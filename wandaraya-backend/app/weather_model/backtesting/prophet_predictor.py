"""Optional Prophet wrapper, isolated from simple baseline implementations."""

from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

from app.weather_model.backtesting.schemas import MonthlyObservation


def make_prophet_predictor(target: str) -> Callable[[list[MonthlyObservation], date], float]:
    """Return a predictor that fits a fresh conservative Prophet per origin."""

    def predict(train: list[MonthlyObservation], target_month: date) -> float:
        # Imported lazily so baseline-only experiments need no Prophet startup.
        from prophet import Prophet

        history = pd.DataFrame(
            {"ds": [item.month for item in train], "y": [item.value for item in train]}
        )
        model = Prophet(
            growth="linear",
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode="additive",
            changepoint_prior_scale=0.05,
            interval_width=0.80,
        )
        model.add_seasonality(
            name="yearly", period=365.25, fourier_order=3, prior_scale=1.0
        )
        model.fit(history)
        value = float(model.predict(pd.DataFrame({"ds": [target_month]})).iloc[0]["yhat"])
        if target == "rainfall_mm":
            return max(0.0, value)
        if not 0.0 <= value <= 45.0:
            raise ValueError("Temperature prediction is outside the accepted range")
        return value

    return predict
