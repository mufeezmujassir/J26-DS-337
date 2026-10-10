from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather_reading import WeatherReading


def none_if_nan(value: Any) -> Any:
    return None if pd.isna(value) else value


class WeatherReadingLoader:
    @staticmethod
    async def upsert(db: AsyncSession, data: dict[str, Any]) -> WeatherReading:
        statement = select(WeatherReading).where(
            WeatherReading.station_id == data["station_id"],
            WeatherReading.observation_date == data["observation_date"],
        )
        reading = (await db.execute(statement)).scalar_one_or_none()
        if reading is None:
            reading = WeatherReading(**data)
            db.add(reading)
        else:
            for field, value in data.items():
                setattr(reading, field, value)
        await db.flush()
        return reading
