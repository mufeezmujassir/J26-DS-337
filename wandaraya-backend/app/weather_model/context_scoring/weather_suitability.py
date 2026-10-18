"""Explainable 0–1 weather suitability scoring, independent of re-ranking."""

from __future__ import annotations

from app.weather_model.context_scoring.activity_weather_rules import get_rule
from app.weather_model.context_scoring.schemas import (
    AttractionWeatherRequest,
    AttractionWeatherScore,
)
from app.weather_model.context_scoring.score_explanations import informational, penalty


DAILY_RAIN_PERIODS = {"daily", "available_3h_intervals"}


class WeatherSuitabilityEngine:
    """Rule-based context score; not a safety warning or a closure decision."""

    @staticmethod
    def _level(score: float) -> str:
        if score >= 0.85:
            return "excellent"
        if score >= 0.65:
            return "good"
        if score >= 0.40:
            return "moderate"
        return "poor"

    def score(self, request: AttractionWeatherRequest) -> AttractionWeatherScore:
        canonical_activity, rule = get_rule(request.activity)
        weather = request.weather
        if weather.status != "available" or weather.reliability_level == "unavailable":
            return AttractionWeatherScore(
                attraction_id=request.attraction_id, activity=canonical_activity, travel_date=request.travel_date,
                status="unknown", suitability_level="unknown", forecast_source=weather.source,
                weather_resolution=weather.resolution, reliability_level=weather.reliability_level,
                explanation="Trustworthy weather information is unavailable; no suitability score was assigned.",
            )

        factors = []
        total_penalty = 0.0
        temperatures = [value for value in (weather.temperature_min_c, weather.temperature_max_c) if value is not None]
        if temperatures:
            temperature = sum(temperatures) / len(temperatures)
            if temperature < rule.ideal_min_c or temperature > rule.ideal_max_c:
                deviation = rule.ideal_min_c - temperature if temperature < rule.ideal_min_c else temperature - rule.ideal_max_c
                amount = min(0.45, deviation * 0.04) * rule.temperature_weight
                total_penalty += amount
                factors.append(penalty("temperature", f"Average available temperature {temperature:.1f}°C is outside the preferred {rule.ideal_min_c}–{rule.ideal_max_c}°C range.", amount))
            else:
                factors.append(informational("temperature", f"Available temperature {temperature:.1f}°C is within the preferred activity range."))
        else:
            factors.append(informational("temperature", "No temperature value is available; temperature did not affect this score."))

        if weather.rainfall_period in DAILY_RAIN_PERIODS:
            if weather.rainfall_mm is not None:
                amount = min(0.60, weather.rainfall_mm / 40.0) * rule.rain_weight
                total_penalty += amount
                if amount:
                    factors.append(penalty("daily_rainfall", f"Daily/interval rainfall of {weather.rainfall_mm:.1f} mm affects this activity.", amount))
            if weather.precipitation_probability is not None:
                amount = weather.precipitation_probability * rule.probability_weight * 0.45
                total_penalty += amount
                if amount:
                    factors.append(penalty("rain_probability", f"Precipitation probability is {weather.precipitation_probability:.0%}.", amount))
        elif weather.rainfall_mm is not None and weather.rainfall_period == "monthly_total":
            factors.append(informational("monthly_rainfall", "Monthly rainfall total is not interpreted as daily rainfall or rain probability."))

        score = round(max(0.0, min(1.0, 1.0 - total_penalty)), 4)
        return AttractionWeatherScore(
            attraction_id=request.attraction_id, activity=canonical_activity, travel_date=request.travel_date,
            status="available", suitability_score=score, suitability_level=self._level(score),
            forecast_source=weather.source, weather_resolution=weather.resolution,
            reliability_level=weather.reliability_level,
            factors=factors,
            explanation="Weather context score is a separate explainable dimension; it does not represent closures, warnings, or other recommendation factors.",
        )
