from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.weather_model.context.monthly_forecast_provider import (
    MonthlyForecastProvider,
)

from app.weather_model.context.schemas import (
    UnifiedWeatherContext,
)
from app.weather_model.context.weather_context_service import (
    WeatherContextService,
)


router = APIRouter(
    prefix="/api/v1/weather",
    tags=["Weather Context"],
)


@router.get(
    "/context/{district_id}",
    response_model=UnifiedWeatherContext,
)
async def get_weather_context(
    district_id: int,
    travel_date: date,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    if district_id <= 0:
        raise HTTPException(
            status_code=422,
            detail="district_id must be positive",
        )

    async def monthly_lookup(
        requested_district_id: int,
        requested_travel_date: date,
    ):
        return await MonthlyForecastProvider.get_monthly_forecast(
            db,
            district_id=requested_district_id,
            travel_date=requested_travel_date,
        )

    service = WeatherContextService(monthly_lookup=monthly_lookup)

    try:
        return await service.get_context(
            district_id=district_id,
            travel_date=travel_date,
            latitude=latitude,
            longitude=longitude,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
