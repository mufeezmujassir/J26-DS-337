import json

import pandas as pd

from app.weather_model.datasets.nasa_power_daily import chronological_split, load_daily_district


def test_daily_loader_cleans_invalid_values_and_keeps_calendar(tmp_path):
    path = tmp_path / "district_78.json"
    path.write_text(json.dumps({
        "sample": {"district_id": 78, "district_name": "Galle"},
        "records": [
            {"date": "2023-12-31", "precipitation_mm": 1, "temperature_min_c": 24, "temperature_max_c": 30},
            {"date": "2024-01-02", "precipitation_mm": -999, "temperature_min_c": 40, "temperature_max_c": 30},
        ],
    }), encoding="utf-8")

    result = load_daily_district(path)

    assert len(result.observations) == 3
    assert result.observations.iloc[1]["date"] == pd.Timestamp("2024-01-01")
    assert pd.isna(result.observations.iloc[2]["rainfall_mm"])
    assert pd.isna(result.observations.iloc[2]["temperature_min_c"])


def test_daily_split_is_chronological_and_non_overlapping():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2023-12-31", "2024-01-01", "2024-12-31", "2025-01-01"]),
        "rainfall_mm": [1, 2, 3, 4],
    })
    train, validation, test = chronological_split(frame)
    assert train["date"].max() < validation["date"].min()
    assert validation["date"].max() < test["date"].min()
