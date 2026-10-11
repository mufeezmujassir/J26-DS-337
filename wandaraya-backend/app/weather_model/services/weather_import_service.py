from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather_station import WeatherStation
from app.models.district import District
from app.weather_model.aggregation.station_weather_builder import StationWeatherBuilder
from app.weather_model.ingestion.weather_reading_loader import (
    WeatherReadingLoader,
    none_if_nan,
)


class HistoricalWeatherImportService:
    """Attach canonical stations and upsert their monthly observations."""

    async def import_data(
        self,
        db: AsyncSession,
        rainfall: pd.DataFrame,
        temperature: pd.DataFrame,
    ) -> pd.DataFrame:
        observations = StationWeatherBuilder.build(rainfall, temperature)
        station_rows = (
            await db.execute(
                select(WeatherStation, District.name)
                .outerjoin(District, WeatherStation.district_id == District.id)
            )
        ).all()
        station_by_name = {
            station.station_name: (station, district_name)
            for station, district_name in station_rows
        }

        unknown = sorted(set(observations["station_name"]) - set(station_by_name))
        if unknown:
            raise ValueError(f"No canonical station found for: {unknown}")

        exported_rows: list[dict] = []
        for row in observations.itertuples(index=False):
            station, district_name = station_by_name[row.station_name]
            data = {
                "station_id": station.station_id,
                "station_name": station.station_name,
                "district_id": station.district_id,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "observation_date": pd.Timestamp(row.date).date(),
                "rainfall_mm": none_if_nan(row.rainfall_mm),
                "temperature_min_c": none_if_nan(row.temperature_min_c),
                "temperature_max_c": none_if_nan(row.temperature_max_c),
                "humidity_percent": None,
                "source": row.source,
            }
            await WeatherReadingLoader.upsert(db, data)
            if station.district_id is not None:
                resolution_status = "RESOLVED"
            elif station.latitude is None or station.longitude is None:
                resolution_status = "PENDING_METADATA"
            else:
                resolution_status = "SPATIAL_FAILURE"
            exported_rows.append(
                {
                    **data,
                    "district_name": district_name,
                    "resolution_status": resolution_status,
                }
            )

        return pd.DataFrame(exported_rows)
