import pandas as pd
import numpy as np
from prophet import Prophet

class WeatherProphetTrainer:
    def __init__(
            self,
            target:str,
    ):
        self.target = target
        self.model=None

    def build_model(self):
        is_rainfall = self.target == "rainfall_mm"

        return Prophet(
            growth="linear",
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode="additive",
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            interval_width=0.80,
        )

    def train(self, train_df: pd.DataFrame):
        data = train_df[["ds", "y"]].dropna().copy()

        if len(data) < 24:
            raise ValueError(
                "Insufficient observed months "
                "for the pilot Prophet model"
            )

        self.model = self.build_model()
        self.model.fit(data)

        return self.model

    def predict(self, dates: pd.DataFrame):
        if self.model is None:
            raise RuntimeError(
                "Train the model before predicting"
            )

        future = dates[["ds"]].copy()

        forecast = self.model.predict(future)

        result = forecast[
            [
                "ds",
                "yhat",
                "yhat_lower",
                "yhat_upper",
            ]
        ].copy()

        # Monthly rainfall cannot be negative.
        # This is an initial physical constraint,
        # not a complete rainfall modeling strategy.
        if self.target == "rainfall_mm":
            for column in (
                "yhat",
                "yhat_lower",
                "yhat_upper",
            ):
                result[column] = result[
                    column
                ].clip(lower=0)

        return result
