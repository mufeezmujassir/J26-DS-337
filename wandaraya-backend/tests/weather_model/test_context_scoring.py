from datetime import date

from app.weather_model.context_scoring.schemas import (
    AttractionWeatherRequest,
    WeatherConditions,
)
from app.weather_model.context_scoring.weather_suitability import WeatherSuitabilityEngine


def request(activity: str, weather: WeatherConditions) -> AttractionWeatherRequest:
    return AttractionWeatherRequest(
        attraction_id=102, activity=activity, travel_date=date(2026, 10, 13), weather=weather
    )


def daily_weather(**changes) -> WeatherConditions:
    values = {
        "status": "available", "source": "openweathermap", "resolution": "three_hourly_aggregated",
        "reliability_level": "live_provider", "rainfall_mm": 0.0,
        "rainfall_period": "available_3h_intervals", "precipitation_probability": 0.0,
        "temperature_min_c": 25.0, "temperature_max_c": 30.0,
    }
    values.update(changes)
    return WeatherConditions(**values)


def test_heavy_rain_penalizes_hiking_more_than_indoor_activity() -> None:
    engine = WeatherSuitabilityEngine()
    weather = daily_weather(rainfall_mm=35.0, precipitation_probability=0.9)
    hiking = engine.score(request("hiking", weather))
    indoor = engine.score(request("indoor_attraction", weather))

    assert hiking.suitability_score is not None and hiking.suitability_score < 0.4
    assert hiking.suitability_level == "poor"
    assert indoor.suitability_score is not None and indoor.suitability_score > hiking.suitability_score


def test_monthly_total_does_not_receive_daily_rain_penalty() -> None:
    engine = WeatherSuitabilityEngine()
    monthly = WeatherConditions(
        status="available", source="approved_model", resolution="monthly", reliability_level="approved_model",
        rainfall_mm=300.0, rainfall_period="monthly_total", temperature_min_c=25.0, temperature_max_c=30.0,
    )
    result = engine.score(request("beach", monthly))

    assert result.suitability_score == 1.0
    assert any(item.factor == "monthly_rainfall" for item in result.factors)


def test_unavailable_weather_returns_unknown_not_low_score() -> None:
    result = WeatherSuitabilityEngine().score(request("wildlife_safari", WeatherConditions(status="unavailable")))
    assert result.status == "unknown"
    assert result.suitability_score is None
    assert result.suitability_level == "unknown"


def test_scoring_is_deterministic_and_activity_aliases_are_supported() -> None:
    engine = WeatherSuitabilityEngine()
    first = engine.score(request("museum", daily_weather(rainfall_mm=15.0)))
    second = engine.score(request("museum", daily_weather(rainfall_mm=15.0)))
    assert first == second
    assert first.activity == "indoor_attraction"
