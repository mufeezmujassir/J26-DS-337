"""Public, read-only semantic candidate weather-context endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.recommendation.context_enrichment.schemas import (
    ContextEnrichmentRequest,
    ContextEnrichmentResponse,
)
from app.recommendation.context_enrichment.service import (
    SemanticWeatherContextEnrichmentService,
)
from app.weather_model.context.monthly_forecast_provider import MonthlyForecastProvider
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.attraction_service import AttractionWeatherSuitabilityService


router = APIRouter(prefix="/api/v1/recommendations", tags=["Recommendation Context"])


@router.post("/context-enrich", response_model=ContextEnrichmentResponse)
async def enrich_semantic_candidates_with_weather(
    payload: ContextEnrichmentRequest,
    db: AsyncSession = Depends(get_db),
) -> ContextEnrichmentResponse:
    """Retrieve semantic Top-K candidates and attach independent weather evidence.

    This endpoint never changes retrieval ordering and never produces a final
    recommendation rank.
    """
    async def monthly_lookup(district_id: int, travel_date):
        return await MonthlyForecastProvider.get_monthly_forecast(
            db, district_id=district_id, travel_date=travel_date
        )

    weather_service = AttractionWeatherSuitabilityService(
        WeatherContextService(monthly_lookup=monthly_lookup)
    )
    service = SemanticWeatherContextEnrichmentService(db, weather_service)
    try:
        return await service.enrich(
            query=payload.query,
            travel_date=payload.travel_date,
            top_k=payload.top_k,
            forecast_mode=payload.forecast_mode,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
