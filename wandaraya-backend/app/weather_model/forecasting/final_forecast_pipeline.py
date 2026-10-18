import json 
import logging
import os
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

from prophet import Prophet
from prophet.serialize import model_to_json, model_from_json
from app.weather_model.forecasting.data_loader import WeatherForecastDataLoader

VALID_TARGETS = {
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
}

VALID_MODELS = {
    "prophet",
    "monthly_climatology",
    "seasonal_naive",
}



class FinalWeatherForecastPipeline:
    def __init__(
            self,
            output_root='data/weather/forecasts/stage6',
    ):
        self.loader = WeatherForecastDataLoader()
        self.root=Path(output_root)

        self.root.mkdir(parents=True, exist_ok=True)


    def load_history(
            self,
            district_id,
            target
    ):
        df=self.loader.load(
            district_id,
            target,
            "full"
        ).copy()

        df["ds"] = pd.to_datetime(
            df["ds"],
            errors="raise",
        )

        df["y"] = pd.to_numeric(
            df["y"],
            errors="raise",
        )

        df = df.sort_values("ds")

        if df["ds"].duplicated().any():
            raise ValueError(
                "Duplicate monthly observations"
            )

        if df["ds"].dt.day.ne(1).any():
            raise ValueError(
                "Expected month-start timestamps"
            )

        if target == "rainfall_mm":
            if (df["y"].dropna() < 0).any():
                raise ValueError(
                    "Negative observed rainfall"
                )

        return df

    def forecast(
        self,
        district_id,
        target,
        selected_model,
        horizon=3,
        approved=False,
    ):
        if target not in VALID_TARGETS:
            raise ValueError(target)

        if selected_model not in VALID_MODELS:
            raise ValueError(selected_model)

        if horizon < 1 or horizon > 12:
            raise ValueError(
                "Horizon must be between 1 and 12"
            )

        history = self.load_history(
            district_id,
            target,
        )

        if history.empty:
            raise ValueError("No history")

        last_calendar_month = history["ds"].max()

        # Preserve the full calendar. Never
        # shift a future forecast into a month
        # whose observation is simply missing.
        observed = history.dropna(
            subset=["y"]
        ).copy()

        if len(observed) < 24:
            raise ValueError(
                "Insufficient observed history"
            )

        last_observed_month = observed["ds"].max()
        latest_month_missing = (
            last_observed_month != last_calendar_month
        )
        training_cutoff = (
            last_observed_month
            if latest_month_missing
            else last_calendar_month
        )

        if latest_month_missing:
            logging.warning(
                "Latest calendar month %s is missing target data; "
                "using the most recent observed month %s for training. "
                "Forecast dates remain aligned to the full calendar.",
                last_calendar_month.date().isoformat(),
                last_observed_month.date().isoformat(),
            )

        future_dates = pd.date_range(
            start=last_calendar_month
            + pd.DateOffset(months=1),
            periods=horizon,
            freq="MS",
        )

        future = pd.DataFrame({
            "ds": future_dates,
        })

        model = None
        parameters = {}

        if selected_model == "prophet":
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
                name="yearly",
                period=365.25,
                fourier_order=3,
                prior_scale=1.0,
            )

            model.fit(
                observed[["ds", "y"]]
            )

            result = model.predict(future)[[
                "ds",
                "yhat",
                "yhat_lower",
                "yhat_upper",
            ]].copy()

            parameters = {
                "fourier_order": 3,
                "seasonality_prior_scale": 1.0,
                "changepoint_prior_scale": 0.05,
            }

        elif selected_model == "monthly_climatology":
            observed["month"] = (
                observed["ds"].dt.month
            )

            means = (
                observed.groupby("month")["y"]
                .mean()
                .to_dict()
            )

            result = future.copy()

            result["yhat"] = (
                result["ds"]
                .dt.month
                .map(means)
            )

            result["yhat_lower"] = np.nan
            result["yhat_upper"] = np.nan

            parameters = {
                "monthly_means": {
                    str(k): float(v)
                    for k, v in means.items()
                }
            }

        else:
            # Same calendar month of the most recent
            # available historical observation. A late
            # calendar month can be blank in the source
            # file while earlier same-month signals are
            # still valid for forecasting.
            observed_by_month = (
                observed
                .sort_values("ds")
                .groupby(observed["ds"].dt.month)["y"]
                .apply(list)
                .to_dict()
            )

            result = future.copy()

            def seasonal_lookup(date):
                month_values = observed_by_month.get(
                    date.month,
                    [],
                )
                if not month_values:
                    return np.nan
                return month_values[-1]

            result["yhat"] = result["ds"].apply(
                seasonal_lookup
            )

            result["yhat_lower"] = np.nan
            result["yhat_upper"] = np.nan

            parameters = {
                "seasonal_lag_months": 12,
                "missing_latest_month_fallback": "latest_same_month_observation",
            }

        if result["yhat"].isna().any():
            raise ValueError(
                "Missing forecast values"
            )

        if not np.isfinite(
            result["yhat"].to_numpy(dtype=float)
        ).all():
            raise ValueError(
                "Non-finite forecast values"
            )

        result["raw_yhat"] = result["yhat"]

        result["training_cutoff"] = (
            training_cutoff.date().isoformat()
        )

        if target == "rainfall_mm":
            result["yhat"] = result["yhat"].clip(
                lower=0
            )

            result["yhat_lower"] = (
                result["yhat_lower"].clip(lower=0)
            )

            result["yhat_upper"] = (
                result["yhat_upper"].clip(lower=0)
            )

        # No clipping for temperatures:
        # flag implausible values for review.
        if target != "rainfall_mm":
            if (
                (result["yhat"] < 0)
                | (result["yhat"] > 45)
            ).any():
                raise ValueError(
                    "Temperature forecast requires review"
                )

        if (
            result["yhat_lower"].notna()
            & result["yhat_upper"].notna()
            & (
                result["yhat_lower"]
                > result["yhat_upper"]
            )
        ).any():
            raise ValueError(
                "Invalid prediction interval"
            )

        result.insert(
            0, "district_id", district_id
        )

        result.insert(
            1, "target", target
        )

        result.insert(
            2, "model", selected_model
        )

        result["training_cutoff"] = (
            result["training_cutoff"].iloc[0]
        )

        result["production_approved"] = bool(
            approved
        )

        # This is a run-specific artifact ID,
        # not a performance metric.
        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")

        run_id = (
            f"d{district_id}_{target}_"
            f"{selected_model}_{timestamp}"
        )

        run_dir = self.root / run_id
        run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        result["run_id"] = run_id

        result.to_csv(
            run_dir / "forecast.csv",
            index=False,
        )

        if model is not None:
            (run_dir / "model.json").write_text(
                model_to_json(model),
                encoding="utf-8",
            )

        metadata = {
            "run_id": run_id,
            "district_id": int(district_id),
            "target": target,
            "selected_model": selected_model,
            "training_start": (
                observed["ds"].min()
                .date().isoformat()
            ),
            "training_cutoff": (
                training_cutoff.date().isoformat()
            ),
            "latest_calendar_month": (
                last_calendar_month.date().isoformat()
            ),
            "latest_observed_month": (
                last_observed_month.date().isoformat()
            ),
            "latest_month_missing": bool(latest_month_missing),
            "training_observations": len(observed),
            "forecast_horizon_months": horizon,
            "production_approved": bool(approved),
            "parameters": parameters,
            "created_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        (run_dir / "metadata.json").write_text(
            json.dumps(
                metadata,
                indent=2,
            ),
            encoding="utf-8",
        )

        return result, metadata

