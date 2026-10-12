"""HTTP API for weather-aware tourism activity suitability."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.weather_model.context.monthly_forecast_provider import (
    MonthlyForecastProvider,
)
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.schemas import IntegratedSuitabilityResponse
from app.weather_model.suitability.suitability_service import (
    WeatherSuitabilityService,
)


router = APIRouter(prefix="/api/v1/weather", tags=["Weather Suitability"])


@router.get(
    "/suitability/{district_id}",
    response_model=IntegratedSuitabilityResponse,
)
async def get_weather_suitability(
    district_id: int,
    travel_date: date,
    activity_type: str,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    if district_id <= 0:
        raise HTTPException(status_code=422, detail="district_id must be positive")

    async def monthly_lookup(
        requested_district_id: int,
        requested_travel_date: date,
    ):
        return await MonthlyForecastProvider.get_monthly_forecast(
            db,
            district_id=requested_district_id,
            travel_date=requested_travel_date,
        )

    service = WeatherSuitabilityService(
        weather_context_service=WeatherContextService(monthly_lookup=monthly_lookup)
    )
    try:
        return await service.evaluate(
            district_id=district_id,
            travel_date=travel_date,
            activity_type=activity_type,
            latitude=latitude,
            longitude=longitude,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
