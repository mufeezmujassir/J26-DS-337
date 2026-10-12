"""Connect read-only Knowledge Base candidates to attraction weather scoring."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.weather_model.suitability.attraction_repository import (
    AttractionWeatherRepository,
)
from app.weather_model.suitability.attraction_schemas import (
    AttractionWeatherBatchRequest,
    AttractionWeatherBatchResponse,
)
from app.weather_model.suitability.attraction_service import (
    AttractionWeatherSuitabilityService,
)
from app.weather_model.suitability.calibration_integration import (
    calibrate_attraction_response,
)


class KnowledgeBaseWeatherService:
    def __init__(
        self,
        db: AsyncSession,
        attraction_weather_service: AttractionWeatherSuitabilityService,
    ):
        self.db = db
        self.attraction_weather_service = attraction_weather_service

    async def evaluate_district(
        self,
        district_id: int,
        travel_date: date,
        limit: int = 50,
    ) -> AttractionWeatherBatchResponse:
        candidates = await AttractionWeatherRepository.get_candidates(
            self.db,
            district_id=district_id,
            limit=limit,
        )
        if not candidates:
            return AttractionWeatherBatchResponse(
                travel_date=travel_date,
                total_attractions=0,
                available_attractions=0,
                unavailable_attractions=0,
                results=[],
            )

        response = await self.attraction_weather_service.evaluate_batch(
            AttractionWeatherBatchRequest(
                travel_date=travel_date,
                attractions=candidates,
            )
        )
        return calibrate_attraction_response(response)
