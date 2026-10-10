import argparse
import logging
from pathlib import Path
import pandas as pd

from app.weather_model.forecasting.final_forecast_pipeline import FinalWeatherForecastPipeline
REGISTRY = Path(
    "data/weather/experiments/stage5/"
    "registry/model_selection_results.csv"
)

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
        "holdout_months",
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
