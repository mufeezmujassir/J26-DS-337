import pandas as pd
from app.weather_model.forecasting.experiment_runner import WeatherExperimentRunner


GALLE_DISTRICT_ID=78

TARGETS = [
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
]

def main():
    print("=" * 65)
    print("WANDARAYA — GALLE WEATHER FORECAST EXPERIMENTS")
    print("=" * 65)

    runner = WeatherExperimentRunner()

    all_results = []

    for target in TARGETS:
        print(f"\nRunning: {target}")

        results = runner.run(
            GALLE_DISTRICT_ID,
            target,
        )

        print(results.to_string(index=False))

        all_results.append(results)

    combined = pd.concat(
        all_results,
        ignore_index=True,
    )

    combined.to_csv(
        runner.output
        / "metrics"
        / "galle_model_comparison.csv",
        index=False,
    )

    print("\n" + "=" * 65)
    print("FINAL GALLE MODEL COMPARISON")
    print("=" * 65)

    print(combined.to_string(index=False))

    print("\nSTAGE 4 PILOT EXPERIMENTS COMPLETED")


if __name__ == "__main__":
    main()