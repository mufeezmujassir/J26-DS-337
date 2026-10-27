"""Prepare forecasting inputs from NASA POWER daily district observations."""

from __future__ import annotations

from pathlib import Path

from app.weather_model.datasets.nasa_power_monthly import load_nasa_power_monthly
from app.weather_model.datasets.prophet_builder import ProphetDatasetBuilder
from app.weather_model.evaluation.coverage_report import WeatherCoverageReporter


INPUT_PATH = Path("data/climate/processed/nasa_power/historical_2010_2025")
MODELING_DIR = Path("data/weather/modeling/nasa_power")
REPORTS_DIR = MODELING_DIR / "reports"


def main() -> None:
    dataset = load_nasa_power_monthly(INPUT_PATH)
    district_weather = dataset.monthly
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = MODELING_DIR / "district_weather_monthly.csv"
    monthly_path.parent.mkdir(parents=True, exist_ok=True)
    district_weather.to_csv(monthly_path, index=False)
    provenance_path = REPORTS_DIR / "nasa_power_provenance.csv"
    dataset.provenance.to_csv(provenance_path, index=False)

    coverage = WeatherCoverageReporter().district_coverage(
        district_weather,
        study_start="2010-01-01",
        study_end="2025-12-01",
    )
    coverage_path = REPORTS_DIR / "district_coverage.csv"
    coverage.to_csv(coverage_path, index=False)

    builder = ProphetDatasetBuilder(
        output_dir=MODELING_DIR / "prophet",
        study_start="2010-01-01",
        study_end="2025-12-01",
        train_end="2021-01-01",
    )
    readiness = builder.build(district_weather)
    readiness_path = REPORTS_DIR / "model_readiness.csv"
    readiness.to_csv(readiness_path, index=False)

    print("Source: NASA POWER daily district observations (2010-2025)")
    print(f"Validated district-month rows: {len(district_weather)}")
    print(f"Districts: {district_weather['district_id'].nunique()}")
    print(f"Readiness rows: {len(readiness)}")
    print(f"Model-ready target series: {int(readiness['model_ready'].sum())}")
    print(f"Saved coverage report: {coverage_path}")
    print(f"Saved readiness report: {readiness_path}")
    print(f"Saved source provenance: {provenance_path}")
    print(f"Saved canonical monthly data: {monthly_path}")
    print(f"Saved Prophet input files: {MODELING_DIR / 'prophet'}")


if __name__ == "__main__":
    main()
