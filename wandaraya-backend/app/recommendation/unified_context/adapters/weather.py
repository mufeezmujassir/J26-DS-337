from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.recommendation.unified_context.schemas import ContextEvidence, EvidenceStatus
from app.weather_model.context.monthly_forecast_provider import MonthlyForecastProvider
from app.weather_model.context.schemas import WeatherSource
from app.weather_model.context.source_selector import WeatherSourceSelector
from app.weather_model.context.weather_context_service import WeatherContextService
from app.weather_model.context_scoring.schemas import AttractionWeatherRequest, WeatherConditions
from app.weather_model.context_scoring.activity_weather_rules import get_rule
from app.weather_model.context_scoring.weather_suitability import WeatherSuitabilityEngine


_QUALITY = {"live_provider": 0.90, "approved_model": 0.65, "historical_climatology": 0.45}
_ACTIVITY_COMPATIBILITY = {
    "beach_relaxation": "beach",
    "swimming": "water_activities",
    "snorkeling": "water_activities",
    "scuba_diving": "water_activities",
    "boating": "water_activities",
    "kayaking": "water_activities",
    "temple_visit": "heritage_site",
    "cultural_experience": "heritage_site",
    "cultural_sightseeing": "heritage_site",
    "sightseeing": "heritage_site",
    "scenic_sightseeing": "heritage_site",
    "nature_sightseeing": "hiking",
}


class WeatherAdapter:
    """Use only real provider/approved-model forecasts as weather evidence.

    Historical climatology is deliberately not scored here because the
    seasonality dimension already owns historical climate evidence.
    """

    source_version = "stage12_5_weather_adapter_v2_daily_nasa_prophet"

    def __init__(self, db: AsyncSession):
        async def monthly_lookup(district_id, travel_date):
            return await MonthlyForecastProvider.get_monthly_forecast(
                db, district_id=district_id, travel_date=travel_date
            )
        self.context_service = WeatherContextService(monthly_lookup=monthly_lookup)
        self.scorer = WeatherSuitabilityEngine()

    async def score_batch(
        self, attractions: list[Attraction], travel_date, activity: str | None
    ) -> dict[int, ContextEvidence]:
        evaluated_at = datetime.now(timezone.utc)
        output: dict[int, ContextEvidence] = {}
        weather_activity = activity
        if activity is not None:
            normalized_activity = activity.strip().casefold().replace("-", "_").replace(" ", "_")
            weather_activity = _ACTIVITY_COMPATIBILITY.get(normalized_activity, activity)
            try:
                get_rule(weather_activity)
            except ValueError:
                return {
                    item.id: ContextEvidence(
                        dimension="weather", status=EvidenceStatus.UNSUPPORTED,
                        source="stage9_6_activity_weather_rules",
                        source_version=self.source_version,
                        evaluated_at=evaluated_at, travel_date=travel_date,
                        explanation=f"The existing weather policy has no rule for activity '{activity}'.",
                        limitations=["No weather score was inferred for an unsupported activity."],
                        missing_data_indicators=["supported_activity_weather_rule"],
                    ) for item in attractions
                }
        contexts: dict[int, object] = {}
        decisions: dict[int, object] = {}
        if activity is not None:
            live: list[Attraction] = []
            daily_groups: dict[int, list[Attraction]] = {}
            monthly_groups: dict[int, list[Attraction]] = {}
            planning_groups: dict[int, list[Attraction]] = {}
            for attraction in attractions:
                if attraction.district_id is None:
                    continue
                decision = WeatherSourceSelector.select(attraction.district_id, travel_date)
                decisions[attraction.id] = decision
                if decision.selected_source is WeatherSource.LIVE_API:
                    live.append(attraction)
                elif decision.selected_source is WeatherSource.DAILY_FORECAST:
                    daily_groups.setdefault(attraction.district_id, []).append(attraction)
                elif decision.selected_source is WeatherSource.MONTHLY_FORECAST:
                    monthly_groups.setdefault(attraction.district_id, []).append(attraction)
                elif decision.selected_source is WeatherSource.CLIMATOLOGY:
                    planning_groups.setdefault(attraction.district_id, []).append(attraction)

            # Live-provider calls do not use the AsyncSession and are safe to
            # overlap. Provider failures remain candidate-local.
            if live:
                live_results = await asyncio.gather(*[
                    self.context_service.get_context(
                        district_id=item.district_id, travel_date=travel_date,
                        latitude=item.latitude, longitude=item.longitude,
                        planning_mode=False,
                    ) for item in live
                ], return_exceptions=True)
                for item, result in zip(live, live_results):
                    contexts[item.id] = result

            for district_id, members in daily_groups.items():
                representative = members[0]
                try:
                    result = await self.context_service.get_context(
                        district_id=district_id, travel_date=travel_date,
                        latitude=representative.latitude, longitude=representative.longitude,
                        planning_mode=False,
                    )
                except Exception as exc:
                    result = exc
                for item in members:
                    contexts[item.id] = result

            # Approved monthly lookups use the shared request session. Query
            # once per district, sequentially, then reuse across candidates.
            for district_id, members in monthly_groups.items():
                representative = members[0]
                try:
                    result = await self.context_service.get_context(
                        district_id=district_id, travel_date=travel_date,
                        latitude=representative.latitude, longitude=representative.longitude,
                        planning_mode=False,
                    )
                except Exception as exc:
                    result = exc
                for item in members:
                    contexts[item.id] = result

            # Beyond the approved-model horizon, retain a clearly labelled
            # historical month-of-year planning estimate instead of dropping
            # the weather layer entirely. Query once per district.
            for district_id, members in planning_groups.items():
                representative = members[0]
                try:
                    result = await self.context_service.get_context(
                        district_id=district_id, travel_date=travel_date,
                        latitude=representative.latitude, longitude=representative.longitude,
                        planning_mode=True,
                    )
                except Exception as exc:
                    result = exc
                for item in members:
                    contexts[item.id] = result

        for attraction in attractions:
            common = dict(
                dimension="weather", evaluated_at=evaluated_at, travel_date=travel_date,
                source_version=self.source_version,
            )
            if activity is None:
                output[attraction.id] = ContextEvidence(
                    **common, status=EvidenceStatus.NOT_AVAILABLE,
                    explanation="No requested activity was supplied, so activity-weather suitability was not computed.",
                    missing_data_indicators=["requested_activity"],
                )
                continue
            if attraction.district_id is None:
                output[attraction.id] = ContextEvidence(
                    **common, status=EvidenceStatus.NOT_AVAILABLE,
                    explanation="The attraction has no verified district for weather-source selection.",
                    missing_data_indicators=["district_id"],
                )
                continue
            decision = decisions[attraction.id]
            if decision.selected_source not in {
                WeatherSource.LIVE_API, WeatherSource.DAILY_FORECAST,
                WeatherSource.MONTHLY_FORECAST, WeatherSource.CLIMATOLOGY,
            }:
                output[attraction.id] = ContextEvidence(
                    **common, status=EvidenceStatus.NOT_AVAILABLE,
                    source=decision.selected_source.value,
                    provenance={
                        "selected_source": decision.selected_source.value,
                        "days_ahead": decision.days_ahead,
                        "forecast_resolution": decision.forecast_resolution,
                    },
                    explanation=decision.message,
                    limitations=[
                        "Historical observations or climatology were not used as a date-specific weather forecast."
                    ],
                    missing_data_indicators=["supported_weather_forecast"],
                )
                continue
            context = contexts[attraction.id]
            if isinstance(context, Exception):
                output[attraction.id] = ContextEvidence(
                    **common, status=EvidenceStatus.ERROR,
                    source=decision.selected_source.value,
                    explanation="The selected weather provider failed for this candidate; no score was assigned.",
                    limitations=[f"{type(context).__name__}: {context}"],
                    missing_data_indicators=["weather_provider_result"],
                )
                continue
            provenance = dict(context.provenance)
            provenance.update({
                "selected_source": context.selected_source,
                "actual_source": context.actual_source,
                "days_ahead": context.days_ahead,
                "resolution": context.resolution,
            })
            if not context.available:
                limitation = context.message
                output[attraction.id] = ContextEvidence(
                    **common, status=EvidenceStatus.NOT_AVAILABLE,
                    source=context.actual_source, provenance=provenance,
                    explanation=context.message,
                    limitations=[limitation],
                    missing_data_indicators=context.missing_targets or ["supported_weather_forecast"],
                    details=context.model_dump(mode="json"),
                )
                continue
            reliability = (
                "live_provider" if context.actual_source == "openweathermap"
                else "historical_climatology" if context.actual_source == "historical_climatology"
                else "approved_model"
            )
            resolution = (
                "three_hourly_aggregated"
                if context.resolution == "three_hourly_aggregated"
                else "daily"
                if context.resolution == "daily"
                else "monthly"
            )
            rainfall_period = context.rainfall_period
            if rainfall_period == "calendar_month":
                rainfall_period = "monthly_total"
            weather = WeatherConditions(
                status="available", source=context.actual_source, resolution=resolution,
                reliability_level=reliability,
                issued_at_utc=context.provenance.get("generated_at_utc"),
                rainfall_mm=context.rainfall_mm, rainfall_period=rainfall_period,
                precipitation_probability=context.precipitation_probability_max,
                temperature_min_c=context.temperature_min_c,
                temperature_max_c=context.temperature_max_c,
            )
            score = self.scorer.score(AttractionWeatherRequest(
                attraction_id=attraction.id, activity=weather_activity,
                travel_date=travel_date, weather=weather,
            ))
            output[attraction.id] = ContextEvidence(
                **common,
                status=EvidenceStatus.AVAILABLE if score.suitability_score is not None else EvidenceStatus.NOT_AVAILABLE,
                score=score.suitability_score,
                confidence=_QUALITY.get(reliability), confidence_label=reliability,
                source=context.actual_source, provenance=provenance,
                explanation=score.explanation,
                limitations=[
                    "Historical monthly climate is a planning estimate, not a day-specific forecast."
                    if context.actual_source == "historical_climatology" else
                    "This is a date-specific long-range model estimate, not a live observation or short-range numerical forecast."
                    if context.actual_source == "nasa_power_daily_prophet" else
                    "Rule-based experimental activity-weather thresholds are not empirically optimized or a safety certification."
                ],
                missing_data_indicators=context.missing_targets,
                details={
                    "conditions": context.model_dump(mode="json"),
                    "suitability_level": score.suitability_level,
                    "factors": [factor.model_dump(mode="json") for factor in score.factors],
                },
            )
        return output
