"""Batch attraction scoring built on one weather-context lookup per location."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from app.weather_model.context.schemas import UnifiedWeatherContext
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES
from app.weather_model.suitability.attraction_schemas import (
    ActivityWeatherScore,
    AttractionWeatherBatchRequest,
    AttractionWeatherBatchResponse,
    AttractionWeatherCandidate,
    AttractionWeatherScore,
)
from app.weather_model.suitability.schemas import WeatherSuitabilityInput
from app.weather_model.suitability.scorer import WeatherSuitabilityScorer


class AttractionWeatherSuitabilityService:
    """Scores supported attraction activities using shared weather context."""

    def __init__(self, context_service: WeatherContextService):
        self.context_service = context_service

    async def evaluate_batch(
        self,
        payload: AttractionWeatherBatchRequest,
    ) -> AttractionWeatherBatchResponse:
        context_cache: dict[tuple[int, float | None, float | None], UnifiedWeatherContext] = {}
        results: list[AttractionWeatherScore] = []

        for attraction in payload.attractions:
            cache_key = (
                attraction.district_id,
                attraction.latitude,
                attraction.longitude,
            )
            context = context_cache.get(cache_key)
            if context is None:
                context = await self.context_service.get_context(
                    district_id=attraction.district_id,
                    travel_date=payload.travel_date,
                    latitude=attraction.latitude,
                    longitude=attraction.longitude,
                )
                context_cache[cache_key] = context

            results.append(self._score_attraction(attraction, context))

        available_attractions = sum(result.available for result in results)
        return AttractionWeatherBatchResponse(
            travel_date=payload.travel_date,
            total_attractions=len(results),
            available_attractions=available_attractions,
            unavailable_attractions=len(results) - available_attractions,
            results=results,
        )

    @classmethod
    def _score_attraction(
        cls,
        attraction: AttractionWeatherCandidate,
        context: UnifiedWeatherContext,
    ) -> AttractionWeatherScore:
        common = {
            "attraction_id": attraction.attraction_id,
            "name": attraction.name,
            "district_id": attraction.district_id,
            "weather_source": context.actual_source,
            "weather_resolution": context.resolution,
            "provenance": {
                **context.provenance,
                "coordinate_source": attraction.coordinate_source,
            },
        }

        if not context.available:
            return AttractionWeatherScore(
                **common,
                available=False,
                suitability="Unknown",
                confidence="unavailable",
                message=context.message,
            )

        activity_scores: list[ActivityWeatherScore] = []
        unsupported: list[str] = []
        risk_factors: list[str] = []

        for activity_type in attraction.activity_types:
            if activity_type not in ACTIVITY_PROFILES:
                unsupported.append(activity_type)
                activity_scores.append(
                    ActivityWeatherScore(
                        activity_type=activity_type,
                        available=False,
                        suitability="Unknown",
                        confidence="unavailable",
                        risk_factors=["Unsupported activity type."],
                    )
                )
                continue

            score = WeatherSuitabilityScorer.score(
                WeatherSuitabilityInput(
                    district_id=attraction.district_id,
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
            activity_scores.append(
                ActivityWeatherScore(
                    activity_type=activity_type,
                    available=score.score is not None,
                    score=score.score,
                    suitability=score.suitability,
                    confidence=score.confidence,
                    risk_factors=score.risk_factors,
                )
            )
            risk_factors.extend(score.risk_factors)

        numeric_scores = [item.score for item in activity_scores if item.score is not None]
        if not numeric_scores:
            message = (
                "No supported activities could be scored for this attraction."
                if unsupported
                else "No usable weather values are available for this attraction."
            )
            return AttractionWeatherScore(
                **common,
                available=False,
                suitability="Unknown",
                confidence="unavailable",
                activity_scores=activity_scores,
                scored_activity_count=0,
                unsupported_activity_types=unsupported,
                risk_factors=cls._unique(risk_factors),
                message=message,
            )

        # Scores are presentation values. Use conventional half-up rounding so
        # an average such as 62.955 is reported as 62.96 rather than Python's
        # banker's-rounding result of 62.95.
        weather_score = float(
            (sum(Decimal(str(value)) for value in numeric_scores) / len(numeric_scores)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        )
        first_scored = next(item for item in activity_scores if item.score is not None)
        message = "Experimental attraction-level weather suitability."
        if unsupported:
            message += " Unsupported activities were excluded from the average."

        return AttractionWeatherScore(
            **common,
            available=True,
            weather_score=weather_score,
            suitability=WeatherSuitabilityScorer._classification(weather_score),
            confidence=first_scored.confidence,
            activity_scores=activity_scores,
            scored_activity_count=len(numeric_scores),
            unsupported_activity_types=unsupported,
            risk_factors=cls._unique(risk_factors),
            message=message,
        )

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))
