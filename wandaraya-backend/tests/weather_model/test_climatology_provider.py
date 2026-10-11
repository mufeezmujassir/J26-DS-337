from datetime import date

import pandas as pd
import pytest

from app.weather_model.context.climatology_provider import (
    ClimatologyProvider,
)


def create_dataset(root, target, district_id, rows):

    directory = root / target
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"district_{district_id}_full.csv"

    pd.DataFrame(rows, columns=["ds", "y"]).to_csv(
        path,
        index=False,
    )

    return path


def test_calculates_historical_monthly_average(tmp_path):

    create_dataset(
        tmp_path,
        "rainfall_mm",
        78,
        [
            ("2021-04-01", 180),
            ("2022-04-01", 210),
            ("2023-04-01", 240),
            ("2024-04-01", 190),
            ("2025-04-01", 230),
            ("2025-05-01", 900),
        ],
    )

    provider = ClimatologyProvider(
        data_root=tmp_path,
        min_years=3,
    )

    result = provider.get_climatology(
        district_id=78,
        travel_date=date(2027, 4, 15),
    )

    assert result.available is True
    assert result.rainfall is not None
    assert result.rainfall.mean == 210.0
    assert result.rainfall.minimum == 180.0
    assert result.rainfall.maximum == 240.0
    assert result.rainfall.observation_years == 5

    assert result.temperature_min is None
    assert result.temperature_max is None

    assert "temperature_min_c" in result.missing_targets
    assert "temperature_max_c" in result.missing_targets


def test_rejects_insufficient_years(tmp_path):

    create_dataset(
        tmp_path,
        "rainfall_mm",
        78,
        [
            ("2024-04-01", 100),
            ("2025-04-01", 120),
        ],
    )

    provider = ClimatologyProvider(
        data_root=tmp_path,
        min_years=3,
    )

    result = provider.get_climatology(
        78,
        date(2027, 4, 15),
    )

    assert result.available is False
    assert result.rainfall is None


def test_missing_district_returns_unavailable(tmp_path):

    provider = ClimatologyProvider(
        data_root=tmp_path,
    )

    result = provider.get_climatology(
        999,
        date(2027, 4, 15),
    )

    assert result.available is False
    assert len(result.missing_targets) == 3


def test_excludes_observations_after_cutoff(tmp_path):

    create_dataset(
        tmp_path,
        "rainfall_mm",
        78,
        [
            ("2021-04-01", 100),
            ("2022-04-01", 110),
            ("2023-04-01", 120),
            ("2024-04-01", 130),
            ("2025-04-01", 1000),
        ],
    )

    provider = ClimatologyProvider(
        data_root=tmp_path,
        min_years=3,
        history_cutoff=date(2024, 12, 31),
    )

    result = provider.get_climatology(
        78,
        date(2027, 4, 15),
    )

    assert result.rainfall is not None
    assert result.rainfall.mean == 115.0
    assert result.rainfall.last_year == 2024


def test_duplicate_month_is_rejected(tmp_path):

    create_dataset(
        tmp_path,
        "rainfall_mm",
        78,
        [
            ("2021-04-01", 100),
            ("2021-04-01", 200),
            ("2022-04-01", 110),
            ("2023-04-01", 120),
        ],
    )

    provider = ClimatologyProvider(
        data_root=tmp_path,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        provider.get_climatology(
            78,
            date(2027, 4, 15),
        )