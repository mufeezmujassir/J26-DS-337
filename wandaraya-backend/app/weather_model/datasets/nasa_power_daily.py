"""Validated daily NASA POWER observations for date-specific weather models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


TARGETS = ("rainfall_mm", "temperature_min_c", "temperature_max_c")
SOURCE_COLUMNS = {
    "precipitation_mm": "rainfall_mm",
    "temperature_min_c": "temperature_min_c",
    "temperature_max_c": "temperature_max_c",
    "temperature_mean_c": "temperature_mean_c",
    "relative_humidity_pct": "relative_humidity_pct",
    "solar_radiation": "solar_radiation",
    "wind_speed_10m": "wind_speed_10m",
}


@dataclass(frozen=True)
class DailyDataset:
    district_id: int
    district_name: str
    observations: pd.DataFrame
    provenance: dict[str, object]


def district_files(source_dir: str | Path) -> list[Path]:
    files = sorted(Path(source_dir).glob("district_*_*.json"))
    if not files:
        raise FileNotFoundError(f"No NASA POWER daily files found in {source_dir}")
    return files


def load_daily_district(path: str | Path) -> DailyDataset:
    source = Path(path)
    raw = source.read_bytes()
    payload = json.loads(raw)
    sample = payload.get("sample") or {}
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError(f"No daily records in {source}")

    frame = pd.DataFrame.from_records(records).rename(columns=SOURCE_COLUMNS)
    required = {"date", *TARGETS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing NASA POWER columns in {source}: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().any() or frame["date"].duplicated().any():
        raise ValueError(f"Invalid or duplicate dates in {source}")
    frame = frame.sort_values("date").reset_index(drop=True)

    for column in SOURCE_COLUMNS.values():
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # These bounds reject provider sentinels and impossible values without
    # deleting legitimate Sri Lankan heavy-rainfall observations.
    valid_ranges = {
        "rainfall_mm": (0.0, 1000.0),
        "temperature_min_c": (-20.0, 60.0),
        "temperature_max_c": (-20.0, 60.0),
        "temperature_mean_c": (-20.0, 60.0),
        "relative_humidity_pct": (0.0, 100.0),
        "solar_radiation": (0.0, 50.0),
        "wind_speed_10m": (0.0, 100.0),
    }
    invalid_counts: dict[str, int] = {}
    for column, (minimum, maximum) in valid_ranges.items():
        if column not in frame:
            continue
        invalid = frame[column].notna() & ~frame[column].between(minimum, maximum)
        invalid_counts[column] = int(invalid.sum())
        frame.loc[invalid, column] = pd.NA
    reversed_temperatures = (
        frame["temperature_min_c"].notna()
        & frame["temperature_max_c"].notna()
        & (frame["temperature_min_c"] > frame["temperature_max_c"])
    )
    invalid_counts["temperature_order"] = int(reversed_temperatures.sum())
    frame.loc[reversed_temperatures, ["temperature_min_c", "temperature_max_c"]] = pd.NA

    expected = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")
    missing_dates = expected.difference(frame["date"])
    if len(missing_dates):
        frame = pd.DataFrame({"date": expected}).merge(frame, on="date", how="left")

    district_id = int(sample["district_id"])
    district_name = str(sample.get("district_name") or district_id)
    provenance = {
        "provider": "NASA POWER",
        "source_file": source.as_posix(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "district_id": district_id,
        "district_name": district_name,
        "latitude": sample.get("latitude"),
        "longitude": sample.get("longitude"),
        "first_date": frame["date"].min().date().isoformat(),
        "last_date": frame["date"].max().date().isoformat(),
        "calendar_days": len(frame),
        "missing_source_dates": len(missing_dates),
        "invalid_values_replaced_with_missing": invalid_counts,
        "spatial_uncertainty": sample.get("spatial_uncertainty"),
    }
    return DailyDataset(district_id, district_name, frame, provenance)


def chronological_split(
    observations: pd.DataFrame,
    *,
    train_end: str = "2023-12-31",
    validation_end: str = "2024-12-31",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return fixed, non-overlapping train/validation/test daily periods."""
    train_cutoff = pd.Timestamp(train_end)
    validation_cutoff = pd.Timestamp(validation_end)
    if train_cutoff >= validation_cutoff:
        raise ValueError("train_end must precede validation_end")
    frame = observations.sort_values("date")
    train = frame[frame["date"] <= train_cutoff].copy()
    validation = frame[(frame["date"] > train_cutoff) & (frame["date"] <= validation_cutoff)].copy()
    test = frame[frame["date"] > validation_cutoff].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("Daily train, validation, and test splits must all be non-empty")
    return train, validation, test
