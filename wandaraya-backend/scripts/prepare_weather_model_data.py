"""Validate district weather data and prepare calendar-complete Prophet datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.weather_model.datasets.prophet_builder import ProphetDatasetBuilder
from app.weather_model.evaluation.coverage_report import WeatherCoverageReporter
from app.weather_model.validation.monthly_quality import validate_district_monthly_weather


INPUT_PATH = Path("data/weather/processed/district_weather_monthly.csv")
MODELING_DIR = Path("data/weather/modeling")
REPORTS_DIR = MODELING_DIR / "reports"


def main() -> None:
    district_weather = pd.read_csv(INPUT_PATH, parse_dates=["observation_date"])
    district_weather = validate_district_monthly_weather(district_weather)

    coverage = WeatherCoverageReporter().district_coverage(district_weather)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    coverage_path = REPORTS_DIR / "corrected_district_coverage.csv"
    coverage.to_csv(coverage_path, index=False)

    builder = ProphetDatasetBuilder(output_dir=MODELING_DIR / "prophet")
    readiness = builder.build(district_weather)
    readiness_path = REPORTS_DIR / "model_readiness.csv"
    readiness.to_csv(readiness_path, index=False)

    print(f"Validated district-month rows: {len(district_weather)}")
    print(f"Districts: {district_weather['district_id'].nunique()}")
    print(f"Readiness rows: {len(readiness)}")
    print(f"Model-ready target series: {int(readiness['model_ready'].sum())}")
    print(f"Saved coverage report: {coverage_path}")
    print(f"Saved readiness report: {readiness_path}")
    print(f"Saved Prophet input files: {MODELING_DIR / 'prophet'}")


if __name__ == "__main__":
    main()
