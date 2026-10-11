"""Read active Tourism Knowledge Base attractions with weather suitability."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.weather_model.context.monthly_forecast_provider import (
    MonthlyForecastProvider,
)
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchResponse,
)
from app.weather_model.suitability.attraction_service import (
    AttractionWeatherSuitabilityService,
)
from app.weather_model.suitability.kb_weather_service import KnowledgeBaseWeatherService


router = APIRouter(prefix="/api/v1/weather", tags=["Knowledge Base Weather"])


@router.get("/attractions", response_model=AttractionWeatherBatchResponse)
async def get_attraction_weather(
    district_id: int = Query(gt=0),
    travel_date: date = Query(...),
    limit: int = Query(default=50, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    async def monthly_lookup(requested_district_id: int, requested_travel_date: date):
        return await MonthlyForecastProvider.get_monthly_forecast(
            db,
            district_id=requested_district_id,
            travel_date=requested_travel_date,
        )

    attraction_weather_service = AttractionWeatherSuitabilityService(
        context_service=WeatherContextService(monthly_lookup=monthly_lookup)
    )
    return await KnowledgeBaseWeatherService(
        db=db,
        attraction_weather_service=attraction_weather_service,
    ).evaluate_district(
        district_id=district_id,
        travel_date=travel_date,
        limit=limit,
    )
