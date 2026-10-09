
from pathlib import Path
import logging

import numpy as np
import pandas as pd

from app.weather_model.forecasting.data_loader import (
    WeatherForecastDataLoader,
)
from app.weather_model.forecasting.prophet_trainer import (
    WeatherProphetTrainer,
)
from app.weather_model.forecasting.seasonal_baseline import (
    SeasonalNaiveBaseline,
)
from app.weather_model.forecasting.monthly_climatology import (
    MonthlyClimatology,
)


logger = logging.getLogger(__name__)

MODELS = (
    "seasonal_naive",
    "monthly_climatology",
    "prophet",
)


class DistrictWeatherBacktester:

    def __init__(self):
        self.loader = WeatherForecastDataLoader()
        self.output = Path(
            "data/weather/experiments/stage5"
        )

        for folder in (
            "validation",
            "holdout",
            "registry",
            "reports",
        ):
            (self.output / folder).mkdir(
                parents=True,
                exist_ok=True,
            )

    def load_history(self, district_id, target):
        # Use the full history rather than a
        # pre-split file for rolling validation.
        df = self.loader.load(
            district_id, target, "full"
        )

        df = df[["ds", "y"]].copy()
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = pd.to_numeric(
            df["y"], errors="coerce"
        )

        if df["ds"].duplicated().any():
            raise ValueError(
                "Duplicate district-month dates"
            )

        return df.sort_values("ds")

    def predict_model(
        self,
        name,
        target,
        train,
        future,
    ):
        if name == "seasonal_naive":
            return SeasonalNaiveBaseline().predict(
                train, future
            )

        if name == "monthly_climatology":
            return MonthlyClimatology().predict(
                train, future
            )

        if name == "prophet":
            trainer = WeatherProphetTrainer(target)

            # Conservative annual seasonality
            # for a short monthly time series.
            original_build = trainer.build_model

            def conservative_model():
                model = original_build()
                model.seasonalities.pop(
                    "yearly", None
                )
                model.yearly_seasonality = False
                model.add_seasonality(
                    name="yearly",
                    period=365.25,
                    fourier_order=3,
                    prior_scale=1.0,
                )
                return model

            trainer.build_model = conservative_model
            trainer.train(train)

            return trainer.predict(future)

        raise ValueError(name)

    def run_fold(
        self,
        history,
        target,
        train_end,
        test_start,
        test_end,
        fold_name,
    ):
        train = history[
            history["ds"] <= pd.Timestamp(train_end)
        ].dropna(subset=["y"]).copy()

        test = history[
            (history["ds"] >= pd.Timestamp(test_start))
            & (history["ds"] <= pd.Timestamp(test_end))
        ].dropna(subset=["y"]).copy()

        if len(train) < 24 or test.empty:
            return None

        predictions = {}
        errors = {}

        for name in MODELS:
            try:
                predicted = self.predict_model(
                    name,
                    target,
                    train,
                    test,
                )

                predictions[name] = predicted[
                    ["ds", "yhat"]
                ].copy()

            except Exception as exc:
                errors[name] = str(exc)
                logger.exception(
                    "Model %s failed in fold %s",
                    name,
                    fold_name,
                )

        # Compare only dates predicted by
        # every candidate model.
        aligned = test[["ds", "y"]].copy()

        for name in MODELS:
            if name not in predictions:
                return {
                    "fold": fold_name,
                    "status": "failed",
                    "reason": str(errors),
                    "metrics": [],
                }

            aligned = aligned.merge(
                predictions[name].rename(
                    columns={"yhat": name}
                ),
                on="ds",
                how="left",
                validate="one_to_one",
            )

        aligned = aligned.replace(
            [np.inf, -np.inf], np.nan
        ).dropna(
            subset=["y", *MODELS]
        )

        if aligned.empty:
            return {
                "fold": fold_name,
                "status": "failed",
                "reason": "No common valid predictions",
                "metrics": [],
            }

        metrics = []

        for name in MODELS:
            error = aligned["y"] - aligned[name]

            metrics.append({
                "fold": fold_name,
                "model": name,
                "mae": float(error.abs().mean()),
                "rmse": float(
                    np.sqrt((error ** 2).mean())
                ),
                "n": len(aligned),
                "absolute_error_sum": float(
                    error.abs().sum()
                ),
                "squared_error_sum": float(
                    (error ** 2).sum()
                ),
            })

        return {
            "fold": fold_name,
            "status": "ok",
            "reason": "",
            "metrics": metrics,
            "predictions": aligned,
        }

    def run(self, district_id, target):
        history = self.load_history(
            district_id, target
        )

        folds = [
            (
                "validation_2023",
                "2022-12-01",
                "2023-01-01",
                "2023-12-01",
            ),
            (
                "validation_2024",
                "2023-12-01",
                "2024-01-01",
                "2024-12-01",
            ),
        ]

        validation = []

        for fold_name, train_end, start, end in folds:
            result = self.run_fold(
                history,
                target,
                train_end,
                start,
                end,
                fold_name,
            )

            if result and result["status"] == "ok":
                validation.extend(result["metrics"])
            else:
                logger.warning(
                    "%s %s: fold %s unavailable",
                    district_id,
                    target,
                    fold_name,
                )

        if not validation:
            raise ValueError(
                "No successful validation folds"
            )

        validation_df = pd.DataFrame(validation)

        # All candidates must be evaluated
        # over the same validation dates.
        scores = (
            validation_df.groupby("model")
            .agg(
                total_absolute_error=(
                    "absolute_error_sum", "sum"
                ),
                total_squared_error=(
                    "squared_error_sum", "sum"
                ),
                total_n=("n", "sum"),
                folds=("fold", "nunique"),
            )
            .reset_index()
        )

        scores["mae"] = (
            scores["total_absolute_error"]
            / scores["total_n"]
        )

        scores["rmse"] = np.sqrt(
            scores["total_squared_error"]
            / scores["total_n"]
        )

        scores = scores.sort_values(
            ["mae", "rmse", "model"]
        )

        winner = scores.iloc[0]["model"]

        # Final holdout: model selection has
        # already happened using 2023–2024.
        train = history[
            history["ds"] < "2025-01-01"
        ].dropna(subset=["y"])

        test = history[
            (history["ds"] >= "2025-01-01")
            & (history["ds"] <= "2025-10-01")
        ].dropna(subset=["y"])

        holdout = self.predict_model(
            winner,
            target,
            train,
            test,
        )

        holdout = test.merge(
            holdout[["ds", "yhat"]],
            on="ds",
            how="inner",
            validate="one_to_one",
        ).dropna(subset=["y", "yhat"])

        if holdout.empty:
            raise ValueError(
                "No valid holdout predictions"
            )

        error = holdout["y"] - holdout["yhat"]

        prefix = f"district_{district_id}_{target}"

        validation_df.to_csv(
            self.output
            / "validation"
            / f"{prefix}_folds.csv",
            index=False,
        )

        scores.to_csv(
            self.output
            / "validation"
            / f"{prefix}_scores.csv",
            index=False,
        )

        holdout.to_csv(
            self.output
            / "holdout"
            / f"{prefix}_predictions.csv",
            index=False,
        )

        return {
            "district_id": district_id,
            "target": target,
            "selected_model": winner,
            "validation_mae": float(
                scores.iloc[0]["mae"]
            ),
            "validation_rmse": float(
                scores.iloc[0]["rmse"]
            ),
            "validation_months": int(
                scores.iloc[0]["total_n"]
            ),
            "validation_folds": int(
                scores.iloc[0]["folds"]
            ),
            "holdout_mae": float(
                error.abs().mean()
            ),
            "holdout_rmse": float(
                np.sqrt((error ** 2).mean())
            ),
            "holdout_months": len(holdout),
            "status": "evaluated",
        }
