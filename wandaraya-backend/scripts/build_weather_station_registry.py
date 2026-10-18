"""Build, persist, and spatially resolve the canonical weather-station registry."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from app.database import AsyncSessionLocal, engine
from app.weather_model.stations.station_district_resolver import WeatherStationDistrictResolver
from app.weather_model.stations.station_loader import WeatherStationLoader
from app.weather_model.stations.station_registry import WeatherStationRegistryBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "weather" / "processed"
METADATA_PATH = PROJECT_ROOT / "data" / "weather" / "stations" / "station_metadata.csv"


def none_if_na(value):
    return None if pd.isna(value) else value


async def main() -> None:
    engine.echo = False
    print("=" * 70)
    print("WANDARAYA WEATHER STATION DISTRICT RESOLUTION")
    print("=" * 70)

    rainfall = pd.read_csv(PROCESSED_DIR / "rainfall_monthly.csv")
    temperature = pd.read_csv(PROCESSED_DIR / "temperature_monthly.csv")
    metadata = pd.read_csv(METADATA_PATH) if METADATA_PATH.exists() else None
    stations = WeatherStationRegistryBuilder.build(rainfall, temperature, metadata)

    resolver = WeatherStationDistrictResolver()
    resolved_count = spatial_failures = pending_count = 0
    output_rows: list[dict] = []

    async with AsyncSessionLocal() as db:
        for row in stations.itertuples(index=False):
            station = await WeatherStationLoader.upsert(
                db,
                {
                    "station_id": row.station_id,
                    "station_name": row.station_name,
                    "latitude": none_if_na(row.latitude),
                    "longitude": none_if_na(row.longitude),
                    "has_rainfall": bool(row.has_rainfall),
                    "has_temperature": bool(row.has_temperature),
                },
            )
            resolution = await resolver.resolve_station_with_status(db, station)
            district = resolution.district
            status = resolution.status
            if status == "PENDING_METADATA":
                pending_count += 1
            elif district and district.found:
                station.district_id = district.district_id
                resolved_count += 1
            else:
                spatial_failures += 1

            output_rows.append({
                "station_id": station.station_id,
                "station_name": station.station_name,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "district_id": station.district_id,
                "district_name": district.district_name if district and district.found else None,
                "resolution_status": status,
                "has_rainfall": station.has_rainfall,
                "has_temperature": station.has_temperature,
            })
        await db.commit()

    output = pd.DataFrame(output_rows).sort_values("station_name")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output.to_csv(PROCESSED_DIR / "weather_stations.csv", index=False)
    coordinate_count = int(output[["latitude", "longitude"]].notna().all(axis=1).sum())
    print(f"Total stations: {len(output)}")
    print(f"Stations with coordinates: {coordinate_count}")
    print(f"Stations without coordinates: {len(output) - coordinate_count}")
    print(f"Resolved by PostGIS: {resolved_count}")
    print(f"Spatial failures: {spatial_failures}")
    print(f"Pending metadata: {pending_count}")
    print(f"Saved: {PROCESSED_DIR / 'weather_stations.csv'}")
    print("CORE STATION DISTRICT RESOLUTION: PASS" if spatial_failures == 0 else "CORE STATION DISTRICT RESOLUTION: CHECK REQUIRED")


if __name__ == "__main__":
    asyncio.run(main())
