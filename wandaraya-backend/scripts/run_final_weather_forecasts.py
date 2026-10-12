import argparse
import logging
from pathlib import Path
import pandas as pd

from app.weather_model.forecasting.final_forecast_pipeline import FinalWeatherForecastPipeline
REGISTRY = Path(
    "data/weather/experiments/stage5/"
    "registry/model_selection_results.csv"
)


def quality_metrics_for(row) -> dict:
    """Attach Stage 5 evidence to the immutable Stage 6 model-run artifact."""
    prefix = f"district_{int(row.district_id)}_{row.target}"
    scores_path = Path("data/weather/experiments/stage5/holdout") / f"{prefix}_scores.csv"
    baseline_holdout_mae: dict[str, float] = {}
    if scores_path.exists():
        scores = pd.read_csv(scores_path)
        required_scores = {"model", "mae"}
        if not required_scores.issubset(scores.columns):
            raise ValueError(f"Holdout score file is malformed: {scores_path}")
        baseline_holdout_mae = {
            str(item.model): float(item.mae)
            for item in scores.itertuples(index=False)
            if str(item.model) in {"seasonal_naive", "monthly_climatology"}
        }

    return {
        "schema_version": "stage9.8.v1",
        "validation_mae": float(row.validation_mae),
        "validation_rmse": float(row.validation_rmse),
        "validation_months": int(row.validation_months),
        "validation_folds": int(row.validation_folds),
        "holdout_mae": float(row.holdout_mae),
        "holdout_rmse": float(row.holdout_rmse),
        "holdout_months": int(row.holdout_months),
        "baseline_holdout_mae": baseline_holdout_mae,
    }

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--district-id",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--horizon",
        type=int,
        default=3,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    registry = pd.read_csv(REGISTRY)

    required = {
        "district_id",
        "target",
        "selected_model",
        "status",
        "validation_folds",
        "validation_months",
        "validation_mae",
        "validation_rmse",
        "holdout_months",
        "holdout_mae",
        "holdout_rmse",
    }

    missing = required - set(registry.columns)

    if missing:
        raise ValueError(
            f"Registry missing columns: {missing}"
        )

    registry = registry[
        registry["status"] == "evaluated"
    ].copy()

    if args.district_id is not None:
        registry = registry[
            registry["district_id"]
            == args.district_id
        ]

    if registry.empty:
        raise ValueError(
            "No matching evaluated models"
        )

    pipeline = FinalWeatherForecastPipeline()

    successes = []
    failures = []
    all_forecasts = []

    print("=" * 65)
    print("WANDARAYA — STAGE 6 FINAL FORECASTING")
    print("=" * 65)

    for row in registry.itertuples(index=False):
        district_id = int(row.district_id)
        target = row.target
        model = row.selected_model

        # Conservative automatic eligibility
        # gate; this is NOT final deployment
        # approval.
        sufficient_validation = (
            int(row.validation_folds) == 2
            and int(row.validation_months) >= 20
            and int(row.holdout_months) >= 9
        )

        print(
            f"\nDistrict {district_id}"
            f" | {target}"
            f" | {model}",
            flush=True,
        )

        try:
            forecast, metadata = pipeline.forecast(
                district_id=district_id,
                target=target,
                selected_model=model,
                horizon=args.horizon,
                approved=False,
            )

            # Stored with the run for a reproducible, post-import quality
            # audit.  Empty baseline evidence is intentionally preserved as
            # empty; Stage 9.8 will reject it from approval rather than infer.
            metadata["parameters"] = {
                **metadata["parameters"],
                "quality_metrics": quality_metrics_for(row),
            }

            all_forecasts.append(forecast)

            successes.append({
                **metadata,
                "validation_gate_passed": (
                    sufficient_validation
                ),
                "status": "trained",
            })

            print(
                forecast[
                    ["ds", "yhat"]
                ].to_string(index=False),
                flush=True,
            )

        except Exception as exc:
            failures.append({
                "district_id": district_id,
                "target": target,
                "selected_model": model,
                "error": str(exc),
            })

            logging.exception(
                "Final training failed"
            )

    reports = pipeline.root / "reports"
    reports.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame(successes).to_csv(
        reports / "training_manifest.csv",
        index=False,
    )

    pd.DataFrame(
        failures,
        columns=[
            "district_id",
            "target",
            "selected_model",
            "error",
        ],
    ).to_csv(
        reports / "failed_training.csv",
        index=False,
    )

    if all_forecasts:
        pd.concat(
            all_forecasts,
            ignore_index=True,
        ).to_csv(
            reports / "all_forecasts.csv",
            index=False,
        )

    print("\n" + "=" * 65)
    print("STAGE 6 SUMMARY")
    print("=" * 65)

    print("Attempted:", len(registry))
    print("Trained:", len(successes))
    print("Failed:", len(failures))
    print(
        "Validation gate passed:",
        sum(
            x["validation_gate_passed"]
            for x in successes
        ),
    )
    print(
        "Production approved:",
        0,
    )
    print("Reports:", reports)


if __name__ == "__main__":
    main()
