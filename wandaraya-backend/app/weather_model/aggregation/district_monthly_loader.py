from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.district_weather_monthly import DistrictWeatherMonthly


def none_if_nan(value: Any) -> Any:
    return None if pd.isna(value) else value


class DistrictMonthlyWeatherLoader:
    @staticmethod
    async def upsert(db: AsyncSession, data: dict[str, Any]) -> DistrictWeatherMonthly:
        statement = select(DistrictWeatherMonthly).where(
            DistrictWeatherMonthly.district_id == data["district_id"],
            DistrictWeatherMonthly.observation_date == data["observation_date"],
        )
        record = (await db.execute(statement)).scalar_one_or_none()
        if record is None:
            record = DistrictWeatherMonthly(**data)
            db.add(record)
        else:
            for field, value in data.items():
                setattr(record, field, value)
        await db.flush()
        return record
