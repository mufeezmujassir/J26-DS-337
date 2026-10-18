from pathlib import Path
import pandas as pd
import argparse
import logging

from app.weather_model.forecasting.district_backtester import DistrictWeatherBacktester

READINESS_FILE = Path(
    "data/weather/modeling/reports/model_readiness.csv"
)

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--district-id",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    readiness = pd.read_csv(READINESS_FILE)

    readiness["model_ready"] = (
        readiness["model_ready"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    eligible = readiness[
        readiness["model_ready"]
    ].copy()

    if args.district_id is not None:
        eligible = eligible[
            eligible["district_id"]
            == args.district_id
        ]

    if eligible.empty:
        raise ValueError(
            "No eligible district/target series"
        )

    runner = DistrictWeatherBacktester()

    successes = []
    failures = []

    print("=" * 65)
    print("WANDARAYA — STAGE 5 DISTRICT BACKTESTING")
    print("=" * 65)

    for row in eligible.itertuples(index=False):
        district_id = int(row.district_id)
        target = row.target

        print(
            f"\nDistrict {district_id}: {target}",
            flush=True,
        )

        try:
            result = runner.run(
                district_id,
                target,
            )

            successes.append(result)

            print(
                "Selected:",
                result["selected_model"],
                "| Validation MAE:",
                round(result["validation_mae"], 4),
                "| Holdout MAE:",
                round(result["holdout_mae"], 4),
                flush=True,
            )

        except Exception as exc:
            failures.append({
                "district_id": district_id,
                "target": target,
                "error": str(exc),
            })

            logging.exception(
                "Failed: district=%s target=%s",
                district_id,
                target,
            )

    output = runner.output / "registry"

    results = pd.DataFrame(successes)
    results.to_csv(
        output / "model_selection_results.csv",
        index=False,
    )

    pd.DataFrame(
        failures,
        columns=["district_id", "target", "error"],
    ).to_csv(
        runner.output
        / "reports"
        / "failed_experiments.csv",
        index=False,
    )

    print("\n" + "=" * 65)
    print("STAGE 5 SUMMARY")
    print("=" * 65)

    print("Eligible series:", len(eligible))
    print("Evaluated series:", len(successes))
    print("Failed series:", len(failures))

    if not results.empty:
        print("\nSelected model distribution:")
        print(
            results["selected_model"]
            .value_counts()
            .to_string()
        )

        print("\nEvaluation summary:")
        print(results.to_string(index=False))

    print("\nResults saved:", output)


if __name__ == "__main__":
    main()
