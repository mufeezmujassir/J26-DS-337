"""Aggregate district-resolved monthly station weather observations."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from app.weather_model.aggregation.monthly_aggregator import (
    aggregate_district_monthly,
)


def main(input_path: Path, output_path: Path) -> None:
    weather = pd.read_csv(input_path, parse_dates=["observation_date"])
    if "district_id" not in weather.columns:
        raise ValueError(
            "Input must be district-resolved and include district_id. "
            "Do not guess district assignments for stations without coordinates."
        )

    aggregated = aggregate_district_monthly(weather)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    aggregated.to_csv(output_path, index=False)
    print(f"District-month rows: {len(aggregated)}")
    print(f"Districts: {aggregated['district_id'].nunique()}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/weather/processed/weather_monthly_resolved.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/weather/processed/district_weather_monthly.csv"),
    )
    arguments = parser.parse_args()
    main(arguments.input, arguments.output)
