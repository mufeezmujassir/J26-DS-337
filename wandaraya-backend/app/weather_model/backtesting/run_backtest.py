"""Run a non-production rolling-origin experiment from existing historical CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.weather_model.backtesting.baselines import (
    monthly_climatology_predict,
    seasonal_naive_predict,
)
from app.weather_model.backtesting.prophet_predictor import make_prophet_predictor
from app.weather_model.backtesting.rolling_origin import rolling_origin_comparison
from app.weather_model.backtesting.schemas import MonthlyObservation
from app.weather_model.forecasting.data_loader import WeatherForecastDataLoader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-id", required=True, type=int)
    parser.add_argument(
        "--target",
        required=True,
        choices=("rainfall_mm", "temperature_min_c", "temperature_max_c"),
    )
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--min-training-months", type=int, default=24)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=("monthly_climatology", "seasonal_naive", "prophet"),
        default=("monthly_climatology", "seasonal_naive", "prophet"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/weather/experiments/stage9_8_4"),
    )
    arguments = parser.parse_args()

    frame = WeatherForecastDataLoader().load(arguments.district_id, arguments.target, "full")
    frame["ds"] = frame["ds"].astype("datetime64[ns]")
    frame["y"] = frame["y"].astype(float)
    observations = [
        MonthlyObservation(month=row.ds.date(), value=float(row.y))
        for row in frame.dropna(subset=["y"]).sort_values("ds").itertuples(index=False)
    ]

    available = {
        "monthly_climatology": monthly_climatology_predict,
        "seasonal_naive": seasonal_naive_predict,
        "prophet": make_prophet_predictor(arguments.target),
    }
    predictors = {name: available[name] for name in arguments.models}
    results = rolling_origin_comparison(
        observations,
        target=arguments.target,
        predictors=predictors,
        horizon_months=arguments.horizon,
        min_training_months=arguments.min_training_months,
        step_months=arguments.step_months,
    )

    output_dir = arguments.output_dir / f"district_{arguments.district_id}_{arguments.target}"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "district_id": arguments.district_id,
        "target": arguments.target,
        "horizon_months": arguments.horizon,
        "results": {name: result.to_dict() for name, result in results.items()},
    }
    (output_dir / "backtest_report.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    with (output_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("model_name", "origin", "target_month", "horizon", "actual", "predicted"),
        )
        writer.writeheader()
        for result in results.values():
            for prediction in result.predictions:
                writer.writerow(
                    {
                        "model_name": prediction.model_name,
                        "origin": prediction.origin.isoformat(),
                        "target_month": prediction.target_month.isoformat(),
                        "horizon": prediction.horizon,
                        "actual": prediction.actual,
                        "predicted": prediction.predicted,
                    }
                )

    print(f"District: {arguments.district_id}")
    print(f"Target: {arguments.target}\n")
    print(f"{'Model':<24} {'Folds':>5} {'MAE':>10} {'RMSE':>10}")
    print("-" * 55)
    for result in results.values():
        print(
            f"{result.model_name:<24} {result.fold_count:>5} "
            f"{str(result.metrics.get('mae', 'n/a')):>10} "
            f"{str(result.metrics.get('rmse', 'n/a')):>10}"
        )
    print("\nSelected model: Pending evaluation")
    print("Production approved: No")
    print("Report:", output_dir / "backtest_report.json")


if __name__ == "__main__":
    main()
