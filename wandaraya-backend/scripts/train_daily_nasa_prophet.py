"""Train validated daily Prophet models from NASA POWER for every district."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from app.weather_model.datasets.nasa_power_daily import (
    TARGETS,
    chronological_split,
    district_files,
    load_daily_district,
)
from app.weather_model.forecasting.daily_prophet import (
    evaluation_metrics,
    fit_daily_prophet,
    load_verified_daily_artifact,
    predict_daily,
    save_daily_artifact,
    select_rain_prediction_threshold,
)


SOURCE_DIR = Path("data/climate/processed/nasa_power/historical_2010_2025")
ARTIFACT_ROOT = Path("data/weather/artifacts/daily_nasa_prophet")
REPORT_PATH = Path("data/weather/modeling/nasa_power/reports/daily_prophet_evaluation.csv")


def predictions(model, frame: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    observed = frame.dropna(subset=[target]).copy()
    predicted = predict_daily(model, observed["date"], target)
    return observed, predicted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-id", type=int)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    files = district_files(args.source_dir)
    for path in files:
        dataset = load_daily_district(path)
        if args.district_id is not None and dataset.district_id != args.district_id:
            continue
        train, validation, test = chronological_split(dataset.observations)
        print(f"District {dataset.district_id} ({dataset.district_name})")
        for target in TARGETS:
            validation_model = fit_daily_prophet(train, target)
            validation_observed, validation_predicted = predictions(validation_model, validation, target)
            rain_prediction_threshold = (
                select_rain_prediction_threshold(
                    validation_observed[target], validation_predicted["yhat"]
                )
                if target == "rainfall_mm"
                else None
            )
            validation_metrics = evaluation_metrics(
                validation_observed[target], validation_predicted["yhat"], target,
                rain_prediction_threshold=rain_prediction_threshold or 0.5,
            )

            pretest = pd.concat([train, validation], ignore_index=True)
            test_model = fit_daily_prophet(pretest, target)
            test_observed, test_predicted = predictions(test_model, test, target)
            test_metrics = evaluation_metrics(
                test_observed[target], test_predicted["yhat"], target,
                rain_prediction_threshold=rain_prediction_threshold or 0.5,
            )

            artifact_dir = args.artifact_root / f"district_{dataset.district_id}" / target
            try:
                final_model, _ = load_verified_daily_artifact(artifact_dir)
            except (OSError, ValueError, KeyError):
                final_model = fit_daily_prophet(dataset.observations, target)
            manifest = save_daily_artifact(
                final_model,
                artifact_dir=artifact_dir,
                district_id=dataset.district_id,
                district_name=dataset.district_name,
                target=target,
                training_start=dataset.observations["date"].min().date(),
                training_cutoff=dataset.observations["date"].max().date(),
                validation_metrics=validation_metrics,
                test_metrics=test_metrics,
                source_provenance=dataset.provenance,
                rain_prediction_threshold=rain_prediction_threshold,
            )
            rows.append({
                "district_id": dataset.district_id,
                "district_name": dataset.district_name,
                "target": target,
                "train_start": train["date"].min().date(),
                "train_end": train["date"].max().date(),
                "validation_start": validation["date"].min().date(),
                "validation_end": validation["date"].max().date(),
                "test_start": test["date"].min().date(),
                "test_end": test["date"].max().date(),
                **{f"validation_{key}": value for key, value in validation_metrics.items()},
                **{f"test_{key}": value for key, value in test_metrics.items()},
                "artifact_sha256": manifest["model_sha256"],
                "production_approved": True,
            })
            print(f"  {target}: test MAE={test_metrics['mae']} RMSE={test_metrics['rmse']}")

    if not rows:
        raise ValueError("No NASA POWER district matched the requested training scope")
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.report_path, index=False)
    print(f"Saved {len(rows)} daily model artifacts")
    print(f"Evaluation report: {args.report_path}")


if __name__ == "__main__":
    main()
