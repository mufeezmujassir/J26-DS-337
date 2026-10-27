"""Build canonical district-month weather observations from NASA POWER daily data.

NASA POWER rainfall is a daily total, so monthly rainfall is the sum of complete
daily observations. Daily minimum/maximum/mean temperatures are averaged to
produce the corresponding monthly climate values used by the existing models.
Incomplete target-months remain missing; they are never silently scaled or
imputed at this ingestion boundary.
"""

from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.weather_model.validation.monthly_quality import (
    validate_district_monthly_weather,
)


NASA_REQUIRED_DAILY_COLUMNS = (
    "precipitation_mm",
    "temperature_min_c",
    "temperature_max_c",
)
NASA_OPTIONAL_DAILY_COLUMNS = (
    "temperature_mean_c",
    "relative_humidity_pct",
    "solar_radiation",
    "wind_speed_10m",
)


@dataclass(frozen=True)
class NasaPowerMonthlyDataset:
    monthly: pd.DataFrame
    provenance: pd.DataFrame


def load_nasa_power_monthly(source_dir: str | Path) -> NasaPowerMonthlyDataset:
    """Load every processed district JSON and return monthly data + provenance."""
    source = Path(source_dir)
    files = sorted(source.glob("district_*_*.json"))
    if not files:
        raise FileNotFoundError(f"No NASA POWER district files found in {source}")

    monthly_parts: list[pd.DataFrame] = []
    provenance_rows: list[dict[str, object]] = []
    seen_districts: set[int] = set()

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        sample = payload.get("sample") or {}
        metadata = payload.get("metadata") or {}
        records = payload.get("records")
        district_id = int(sample["district_id"])
        if district_id in seen_districts:
            raise ValueError(f"Duplicate NASA POWER district {district_id}: {path}")
        seen_districts.add(district_id)
        if not isinstance(records, list) or not records:
            raise ValueError(f"NASA POWER file has no records: {path}")

        daily = pd.DataFrame.from_records(records)
        required = {"date", *NASA_REQUIRED_DAILY_COLUMNS}
        missing = required - set(daily.columns)
        if missing:
            raise ValueError(f"{path} is missing NASA fields: {sorted(missing)}")
        daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
        if daily["date"].isna().any() or daily["date"].duplicated().any():
            raise ValueError(f"{path} contains invalid or duplicate daily dates")
        daily = daily.sort_values("date").reset_index(drop=True)
        for column in (*NASA_REQUIRED_DAILY_COLUMNS, *NASA_OPTIONAL_DAILY_COLUMNS):
            if column in daily:
                daily[column] = pd.to_numeric(daily[column], errors="coerce")
        if (daily["precipitation_mm"].dropna() < 0).any():
            raise ValueError(f"{path} contains negative precipitation")

        monthly = _aggregate_district(daily)
        monthly.insert(0, "district_name", sample.get("district_name"))
        monthly.insert(0, "district_id", district_id)
        monthly_parts.append(monthly)

        header = metadata.get("header") or {}
        provenance_rows.append(
            {
                "district_id": district_id,
                "district_name": sample.get("district_name"),
                "provider": sample.get("provider", "NASA POWER"),
                "api_name": (header.get("api") or {}).get("name"),
                "api_version": (header.get("api") or {}).get("version"),
                "source_products": ",".join(header.get("sources") or []),
                "latitude": sample.get("latitude"),
                "longitude": sample.get("longitude"),
                "first_daily_date": daily["date"].min().date().isoformat(),
                "last_daily_date": daily["date"].max().date().isoformat(),
                "daily_records": len(daily),
                "monthly_records": len(monthly),
                "response_checksum_sha256": metadata.get("response_checksum_sha256"),
                "source_file": path.as_posix(),
                "spatial_uncertainty": sample.get("spatial_uncertainty"),
                "time_standard": header.get("time_standard"),
            }
        )

    combined = pd.concat(monthly_parts, ignore_index=True)
    combined = validate_district_monthly_weather(combined)
    provenance = pd.DataFrame(provenance_rows).sort_values("district_id").reset_index(drop=True)
    return NasaPowerMonthlyDataset(monthly=combined, provenance=provenance)


def _aggregate_district(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["observation_date"] = frame["date"].dt.to_period("M").dt.to_timestamp()
    rows: list[dict[str, object]] = []
    value_columns = [
        column
        for column in (*NASA_REQUIRED_DAILY_COLUMNS, *NASA_OPTIONAL_DAILY_COLUMNS)
        if column in frame.columns
    ]

    for month, group in frame.groupby("observation_date", sort=True):
        expected_days = monthrange(month.year, month.month)[1]
        row: dict[str, object] = {
            "observation_date": month,
            "expected_daily_records": expected_days,
            "observed_daily_records": len(group),
            "daily_coverage_pct": round(len(group) / expected_days * 100, 2),
        }
        for column in value_columns:
            complete = len(group) == expected_days and group[column].notna().all()
            output_column = "rainfall_mm" if column == "precipitation_mm" else column
            if not complete:
                row[output_column] = None
            elif column == "precipitation_mm":
                row[output_column] = round(float(group[column].sum()), 3)
            else:
                row[output_column] = round(float(group[column].mean()), 3)
        rows.append(row)
    return pd.DataFrame(rows)
