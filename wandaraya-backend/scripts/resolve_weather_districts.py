from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from app.database import AsyncSessionLocal
from app.weather_model.ingestion.district_resolution import resolve_weather_districts


INPUT_PATH = Path("data/weather/processed/weather_monthly_normalized.csv")
OUTPUT_PATH = Path("data/weather/processed/weather_monthly_resolved.csv")


async def main() -> None:
    weather = pd.read_csv(INPUT_PATH, parse_dates=["observation_date"])
    async with AsyncSessionLocal() as db:
        resolved = await resolve_weather_districts(db, weather)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    resolved.to_csv(OUTPUT_PATH, index=False)
    print(f"Rows: {len(resolved)}")
    print(f"Resolved rows: {(resolved['resolution_status'] == 'RESOLVED').sum()}")
    print(f"Unresolved rows: {(resolved['resolution_status'] != 'RESOLVED').sum()}")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
