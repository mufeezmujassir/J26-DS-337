"""Transparent baseline rules that turn weather context into activity suitability."""

from app.weather_model.suitability.activity_profiles import ACTIVITY_PROFILES
from app.weather_model.suitability.schemas import (
    WeatherSuitabilityInput,
    WeatherSuitabilityResult,
)


class WeatherSuitabilityScorer:
    """Rule-based baseline; it is not a safety-warning or closure system."""

    _SUPPORTED_SOURCES = {
        "openweathermap",
        "monthly_forecast",
        "historical_climatology",
    }
    _DAILY_RAIN_PERIODS = {"available_3h_intervals", "daily", "daily_total"}

    @staticmethod
    def _temperature_penalty(
        temperature: float,
        ideal_min: float,
        ideal_max: float,
    ) -> float:
        if ideal_min <= temperature <= ideal_max:
            return 0.0

        deviation = (
            ideal_min - temperature
            if temperature < ideal_min
            else temperature - ideal_max
        )
        return min(30.0, deviation * 4.0)

    @staticmethod
    def _confidence(weather_source: str) -> str:
        return {
            "openweathermap": "high",
            "monthly_forecast": "medium",
            "historical_climatology": "low",
        }[weather_source]

    @staticmethod
    def _classification(score: float) -> str:
        if score >= 70:
            return "Suitable"
        if score >= 40:
            return "Moderate"
        return "Unsuitable"

    @classmethod
    def score(
        cls,
        data: WeatherSuitabilityInput,
    ) -> WeatherSuitabilityResult:
        profile = ACTIVITY_PROFILES.get(data.activity_type)
        if profile is None:
            raise ValueError(f"Unsupported activity type: {data.activity_type}")

        if data.weather_source not in cls._SUPPORTED_SOURCES:
            return cls._unavailable(
                data,
                "Unsupported or unavailable weather source.",
            )

        if not any(
            value is not None
            for value in (
                data.temperature_min_c,
                data.temperature_max_c,
                data.rainfall_mm,
                data.precipitation_probability_max,
            )
        ):
            return cls._unavailable(data, "No usable weather observations are available.")

        penalties: list[float] = []
        risk_factors: list[str] = []

        # The minimum temperature is the conservative baseline signal used by
        # the supplied pilot rules. If it is absent, use the maximum instead.
        temperature = data.temperature_min_c
        if temperature is None:
            temperature = data.temperature_max_c
        if temperature is not None:
            temperature_penalty = cls._temperature_penalty(
                temperature,
                profile.ideal_temp_min_c,
                profile.ideal_temp_max_c,
            ) * profile.temperature_sensitivity
            penalties.append(temperature_penalty)
            if temperature_penalty > 0:
                risk_factors.append("Temperature is outside the activity's ideal range.")

        # A monthly total must never be interpreted as a single-day rainfall
        # amount. Until a monthly anomaly/percentile feature exists, monthly
        # forecast and climatology rainfall contribute no rain penalty.
        can_score_daily_rain = (
            data.weather_source == "openweathermap"
            and data.rainfall_period in cls._DAILY_RAIN_PERIODS
        )
        if can_score_daily_rain:
            rain_penalty = 0.0
            if data.rainfall_mm is not None:
                rain_penalty += data.rainfall_mm * 2.0
            if data.precipitation_probability_max is not None:
                rain_penalty += data.precipitation_probability_max * 40.0
            rain_penalty = min(60.0, rain_penalty) * profile.rain_sensitivity
            penalties.append(rain_penalty)
            if rain_penalty > 0:
                risk_factors.append("Rainfall or precipitation probability may affect this activity.")
        elif data.rainfall_mm is not None and data.weather_source != "openweathermap":
            risk_factors.append(
                "Monthly rainfall is reported but is not treated as daily rainfall."
            )

        score = round(max(0.0, 100.0 - sum(penalties)), 2)
        suitability = cls._classification(score)
        return WeatherSuitabilityResult(
            district_id=data.district_id,
            travel_date=data.travel_date,
            activity_type=data.activity_type,
            score=score,
            confidence=cls._confidence(data.weather_source),
            suitability=suitability,
            weather_source=data.weather_source,
            risk_factors=risk_factors,
            explanation=(
                "Experimental rule-based weather suitability score. It does not "
                "replace official weather warnings, park closures, or sea-safety advisories."
            ),
        )

    @classmethod
    def _unavailable(
        cls,
        data: WeatherSuitabilityInput,
        message: str,
    ) -> WeatherSuitabilityResult:
        return WeatherSuitabilityResult(
            district_id=data.district_id,
            travel_date=data.travel_date,
            activity_type=data.activity_type,
            confidence="unavailable",
            suitability="Unknown",
            weather_source=data.weather_source,
            explanation=message,
        )
