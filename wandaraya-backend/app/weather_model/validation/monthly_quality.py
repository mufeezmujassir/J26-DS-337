"""Validation helpers for the canonical district-month weather dataset."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


MONTHLY_TARGET_COLUMNS = (
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
)


def normalize_month_starts(
    frame: pd.DataFrame,
    *,
    date_column: str = "observation_date",
) -> pd.DataFrame:
    """Return a copy whose dates are valid first-of-month timestamps."""
    if date_column not in frame.columns:
        raise ValueError(f"Missing required date column: {date_column}")

    result = frame.copy()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    if result[date_column].isna().any():
        raise ValueError(f"{date_column} contains invalid or missing dates.")

    result[date_column] = result[date_column].dt.to_period("M").dt.to_timestamp()
    return result


def validate_unique_keys(
    frame: pd.DataFrame,
    keys: Iterable[str],
) -> None:
    """Fail early when a supposedly monthly dataset has duplicate keys."""
    key_columns = list(keys)
    missing = set(key_columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Cannot validate missing key columns: {sorted(missing)}")

    duplicates = frame.duplicated(key_columns, keep=False)
    if duplicates.any():
        sample = frame.loc[duplicates, key_columns].head(10).to_dict("records")
        raise ValueError(
            f"Duplicate monthly keys for {key_columns}; sample: {sample}"
        )


def validate_district_monthly_weather(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a district-month dataset without treating absent values as zero."""
    required = {"district_id", "observation_date", *MONTHLY_TARGET_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"District weather data is missing columns: {sorted(missing)}")

    result = normalize_month_starts(frame)
    if result["district_id"].isna().any():
        raise ValueError("district_id contains missing values.")
    validate_unique_keys(result, ("district_id", "observation_date"))

    for column in MONTHLY_TARGET_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    if (result["rainfall_mm"].dropna() < 0).any():
        raise ValueError("rainfall_mm cannot contain negative values.")

    temperatures = result[["temperature_min_c", "temperature_max_c"]].dropna()
    if (temperatures["temperature_min_c"] > temperatures["temperature_max_c"]).any():
        raise ValueError("temperature_min_c cannot be greater than temperature_max_c.")

    return result.sort_values(["district_id", "observation_date"]).reset_index(drop=True)
