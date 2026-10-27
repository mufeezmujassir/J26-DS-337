import json

import pytest
import pandas as pd

from app.weather_model.datasets.nasa_power_monthly import load_nasa_power_monthly
from app.weather_model.backtesting.observation_loader import (
    load_monthly_observations_from_csv,
)


def write_district(path, *, district_id=78, records):
    payload = {
        "metadata": {
            "header": {
                "api": {"name": "POWER Daily API", "version": "v2.10.0"},
                "sources": ["MERRA2", "POWER"],
                "time_standard": "UTC",
            },
            "response_checksum_sha256": "abc",
        },
        "sample": {
            "district_id": district_id,
            "district_name": "Galle",
            "provider": "NASA POWER",
            "latitude": 6.03,
            "longitude": 80.21,
        },
        "records": records,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def january_records(days=31):
    return [
        {
            "date": f"2024-01-{day:02d}",
            "precipitation_mm": 1.0,
            "temperature_min_c": 20.0 + day / 100,
            "temperature_max_c": 30.0 + day / 100,
            "temperature_mean_c": 25.0 + day / 100,
        }
        for day in range(1, days + 1)
    ]


def test_aggregates_complete_daily_month_without_inventing_values(tmp_path):
    write_district(tmp_path / "district_78_20240101_20240131.json", records=january_records())

    dataset = load_nasa_power_monthly(tmp_path)

    row = dataset.monthly.iloc[0]
    assert row["rainfall_mm"] == 31.0
    assert row["temperature_min_c"] == pytest.approx(20.16)
    assert row["temperature_max_c"] == pytest.approx(30.16)
    assert row["observed_daily_records"] == 31
    assert dataset.provenance.iloc[0]["provider"] == "NASA POWER"


def test_incomplete_month_is_kept_but_targets_are_missing(tmp_path):
    write_district(tmp_path / "district_78_partial.json", records=january_records(30))

    row = load_nasa_power_monthly(tmp_path).monthly.iloc[0]

    assert row["daily_coverage_pct"] < 100
    assert row["rainfall_mm"] != row["rainfall_mm"]
    assert row["temperature_min_c"] != row["temperature_min_c"]


def test_duplicate_district_files_are_rejected(tmp_path):
    write_district(tmp_path / "district_78_a.json", records=january_records())
    write_district(tmp_path / "district_78_b.json", records=january_records())

    with pytest.raises(ValueError, match="Duplicate NASA POWER district"):
        load_nasa_power_monthly(tmp_path)


def test_candidate_loader_reads_only_requested_nasa_district_and_target(tmp_path):
    path = tmp_path / "monthly.csv"
    pd.DataFrame(
        [
            {"district_id": 78, "observation_date": "2024-01-01", "rainfall_mm": 31.0},
            {"district_id": 78, "observation_date": "2024-02-01", "rainfall_mm": 29.0},
            {"district_id": 79, "observation_date": "2024-01-01", "rainfall_mm": 99.0},
        ]
    ).to_csv(path, index=False)

    rows = load_monthly_observations_from_csv(path, 78, "rainfall_mm")

    assert [row.value for row in rows] == [31.0, 29.0]
