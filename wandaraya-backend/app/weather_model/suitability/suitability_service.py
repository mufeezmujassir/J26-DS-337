"""Connect weather-source selection with activity-suitability scoring."""

from __future__ import annotations

from datetime import date

from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES
from app.weather_model.suitability.schemas import (
    IntegratedSuitabilityResponse,
    WeatherSuitabilityInput,
)
from app.weather_model.suitability.scorer import WeatherSuitabilityScorer


class WeatherSuitabilityService:
    """Orchestrates Stage 8 weather context and Stage 9 scoring responsibilities."""

    def __init__(self, weather_context_service: WeatherContextService):
        self.weather_context_service = weather_context_service

    async def evaluate(
        self,
        district_id: int,
        travel_date: date,
        activity_type: str,
        latitude: float | None = None,
        longitude: float | None = None,
        planning_mode: bool = False,
    ) -> IntegratedSuitabilityResponse:
        if activity_type not in ACTIVITY_PROFILES:
            raise ValueError(f"Unsupported activity type: {activity_type}")

        context = await self.weather_context_service.get_context(
            district_id=district_id,
            travel_date=travel_date,
            latitude=latitude,
            longitude=longitude,
            planning_mode=planning_mode,
        )

        response_fields = {
            "district_id": context.district_id,
            "travel_date": context.travel_date,
            "activity_type": activity_type,
            "weather_source": context.actual_source,
            "weather_resolution": context.resolution,
            "rainfall_mm": context.rainfall_mm,
            "rainfall_period": context.rainfall_period,
            "temperature_min_c": context.temperature_min_c,
            "temperature_max_c": context.temperature_max_c,
            "missing_targets": context.missing_targets,
            "provenance": context.provenance,
        }

        if not context.available:
            return IntegratedSuitabilityResponse(
                **response_fields,
                available=False,
                score=None,
                suitability="Unknown",
                confidence="unavailable",
                explanation=context.message,
            )

        score = WeatherSuitabilityScorer.score(
            WeatherSuitabilityInput(
                district_id=context.district_id,
                travel_date=context.travel_date,
                activity_type=activity_type,
                weather_source=context.actual_source,
                rainfall_mm=context.rainfall_mm,
                rainfall_period=context.rainfall_period,
                temperature_min_c=context.temperature_min_c,
                temperature_max_c=context.temperature_max_c,
                precipitation_probability_max=(
                    context.precipitation_probability_max
                ),
            )
        )

        return IntegratedSuitabilityResponse(
            **response_fields,
            available=score.score is not None,
            score=score.score,
            suitability=score.suitability,
            confidence=score.confidence,
            risk_factors=score.risk_factors,
            explanation=score.explanation,
        )
