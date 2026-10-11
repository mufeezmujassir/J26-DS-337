"""Batch API for attraction-level weather suitability."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.weather_model.context.monthly_forecast_provider import (
    MonthlyForecastProvider,
)
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchRequest,
    AttractionWeatherBatchResponse,
)
from app.weather_model.suitability.attraction_service import (
    AttractionWeatherSuitabilityService,
)


router = APIRouter(prefix="/api/v1/weather", tags=["Attraction Weather Suitability"])


@router.post(
    "/suitability/batch",
    response_model=AttractionWeatherBatchResponse,
)
async def evaluate_attraction_weather_batch(
    payload: AttractionWeatherBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    async def monthly_lookup(district_id: int, travel_date):
        return await MonthlyForecastProvider.get_monthly_forecast(
            db,
            district_id=district_id,
            travel_date=travel_date,
        )

    service = AttractionWeatherSuitabilityService(
        context_service=WeatherContextService(monthly_lookup=monthly_lookup)
    )
    return await service.evaluate_batch(payload)
