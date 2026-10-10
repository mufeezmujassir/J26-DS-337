from pathlib import Path
import pandas as pd

from app.weather_model.forecasting.data_loader import WeatherForecastDataLoader
from app.weather_model.forecasting.prophet_trainer import WeatherProphetTrainer
from app.weather_model.forecasting.seasonal_baseline import SeasonalNaiveBaseline
from app.weather_model.forecasting.evaluator import evaluate_forecast
from app.weather_model.forecasting.plotting import plot_forecast_comparison

class WeatherExperimentRunner:
    def __init__(
            self
    ):
        self.loader = WeatherForecastDataLoader()
        self.output = Path(
            "/app/data/weather/experiments"
        )

        for folder in (
            "metrics",
            "predictions",
            "models",
            "plots",
        ):
            (self.output / folder).mkdir(
                parents=True,
                exist_ok=True,
            )

    def run(self, district_id, target):
        train = self.loader.load(
            district_id, target, "train"
        )

        test = self.loader.load(
            district_id, target, "test"
        )

        # Seasonal-naive baseline
        baseline = SeasonalNaiveBaseline()
        baseline_predictions = baseline.predict(
            train, test
        )

        # Prophet model
        trainer = WeatherProphetTrainer(target)
        trainer.train(train)

        prophet_predictions = trainer.predict(test)

        # Evaluate both models on identical
        # observed dates with baseline predictions.
        comparison_dates = (
            test[["ds", "y"]]
            .merge(
                baseline_predictions,
                on="ds",
                how="left",
            )
            .dropna(subset=["y", "yhat"])["ds"]
        )

        actual = test[
            test["ds"].isin(comparison_dates)
        ]

        baseline_metrics = evaluate_forecast(
            actual,
            baseline_predictions,
            "seasonal_naive",
        )

        prophet_metrics = evaluate_forecast(
            actual,
            prophet_predictions,
            "prophet",
        )

        results = pd.DataFrame([
            {
                "district_id": district_id,
                "target": target,
                **baseline_metrics,
            },
            {
                "district_id": district_id,
                "target": target,
                **prophet_metrics,
            },
        ])

        prefix = (
            f"district_{district_id}_{target}"
        )

        results.to_csv(
            self.output
            / "metrics"
            / f"{prefix}_metrics.csv",
            index=False,
        )

        prophet_predictions.to_csv(
            self.output
            / "predictions"
            / f"{prefix}_prophet.csv",
            index=False,
        )

        plot_forecast_comparison(
            actual,
            prophet_predictions,
            baseline_predictions,
            f"Galle District {district_id}: {target} forecast comparison",
            self.output
            / "plots"
            / f"{prefix}_comparison.png",
        )

        baseline_predictions.to_csv(
            self.output
            / "predictions"
            / f"{prefix}_seasonal_naive.csv",
            index=False,
        )

        # Persist Prophet's fitted model using
        # Prophet's supported serialization API.
        from prophet.serialize import model_to_json

        model_path = (
            self.output
            / "models"
            / f"{prefix}_prophet.json"
        )

        model_path.write_text(
            model_to_json(trainer.model),
            encoding="utf-8",
        )

        return results
