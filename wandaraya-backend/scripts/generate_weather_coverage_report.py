from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.weather_model.evaluation.coverage_report import WeatherCoverageReporter


INPUT_PATH = Path("data/weather/processed/weather_monthly_resolved.csv")
OUTPUT_PATH = Path("data/weather/processed/district_weather_coverage.csv")


def main() -> None:
    weather = pd.read_csv(INPUT_PATH, parse_dates=["observation_date"])
    reporter = WeatherCoverageReporter()
    coverage = reporter.district_coverage(weather)
    coverage = reporter.add_coverage_percentages(coverage)
    coverage["temperature_months"] = coverage[["temp_min_count", "temp_max_count"]].min(axis=1)
    coverage["rainfall_trainable"] = coverage["rainfall_count"] >= 48
    coverage["temperature_trainable"] = coverage["temperature_months"] >= 48
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(OUTPUT_PATH, index=False)
    print(coverage.to_string(index=False))
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
