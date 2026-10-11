"""Persist canonical station weather readings and rebuild district monthly data."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from app.database import AsyncSessionLocal, engine
from app.weather_model.aggregation.monthly_aggregator import aggregate_district_monthly
from app.weather_model.aggregation.district_monthly_loader import (
    DistrictMonthlyWeatherLoader,
    none_if_nan,
)
from app.weather_model.services.weather_import_service import HistoricalWeatherImportService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "weather" / "processed"


async def main() -> None:
    engine.echo = False
    print("=" * 70)
    print("WANDARAYA DISTRICT WEATHER FOUNDATION")
    print("=" * 70)
    rainfall = pd.read_csv(PROCESSED_DIR / "rainfall_monthly.csv", parse_dates=["date"])
    temperature = pd.read_csv(PROCESSED_DIR / "temperature_monthly.csv", parse_dates=["date"])

    async with AsyncSessionLocal() as db:
        readings = await HistoricalWeatherImportService().import_data(db, rainfall, temperature)
        await db.commit()

    readings["observation_date"] = pd.to_datetime(readings["observation_date"])
    resolved_path = PROCESSED_DIR / "weather_monthly_resolved.csv"
    readings.to_csv(resolved_path, index=False)
    district_monthly = aggregate_district_monthly(readings)
    district_path = PROCESSED_DIR / "district_weather_monthly.csv"
    district_monthly.to_csv(district_path, index=False)

    async with AsyncSessionLocal() as db:
        for row in district_monthly.itertuples(index=False):
            await DistrictMonthlyWeatherLoader.upsert(
                db,
                {
                    "district_id": int(row.district_id),
                    "observation_date": pd.Timestamp(row.observation_date).date(),
                    "rainfall_mm": none_if_nan(row.rainfall_mm),
                    "temperature_min_c": none_if_nan(row.temperature_min_c),
                    "temperature_max_c": none_if_nan(row.temperature_max_c),
                    "temperature_avg_c": none_if_nan(row.temperature_avg_c),
                    "rainfall_station_count": int(row.rainfall_station_count),
                    "temperature_station_count": int(row.temperature_station_count),
                },
            )
        await db.commit()

    print(f"Station-month rows: {len(readings)}")
    print(f"Resolved readings: {(readings['district_id'].notna()).sum()}")
    print(f"Pending readings: {(readings['district_id'].isna()).sum()}")
    print(f"District-month rows: {len(district_monthly)}")
    print(f"Districts represented: {district_monthly['district_id'].nunique()}")
    print(f"Saved: {resolved_path}")
    print(f"Saved: {district_path}")
    print("STAGE 2: PASS")


if __name__ == "__main__":
    asyncio.run(main())
