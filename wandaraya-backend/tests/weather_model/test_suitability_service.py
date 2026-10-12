from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.weather_model.context.schemas import UnifiedWeatherContext
from app.weather_model.suitability.suitability_service import (
    WeatherSuitabilityService,
)


REFERENCE_DATE = date(2026, 10, 11)
TRAVEL_DATE = date(2026, 10, 13)


def make_context(**overrides) -> UnifiedWeatherContext:
    values = {
        "district_id": 78,
        "travel_date": TRAVEL_DATE,
        "reference_date": REFERENCE_DATE,
        "days_ahead": 2,
        "selected_source": "live_api",
        "actual_source": "openweathermap",
        "available": True,
        "resolution": "three_hourly_aggregated",
        "rainfall_mm": 2.19,
        "rainfall_period": "available_3h_intervals",
        "temperature_min_c": 26.9,
        "temperature_max_c": 30.23,
        "precipitation_probability_max": 0.98,
        "provenance": {"provider": "OpenWeatherMap"},
        "message": "Available",
    }
    values.update(overrides)
    return UnifiedWeatherContext(**values)


@pytest.mark.asyncio
async def test_live_context_is_scored():
    context_service = AsyncMock()
    context_service.get_context.return_value = make_context()
    service = WeatherSuitabilityService(context_service)

    result = await service.evaluate(78, TRAVEL_DATE, "hiking", 6.0535, 80.2210)

    assert result.available is True
    assert result.weather_source == "openweathermap"
    assert result.score == 56.42
    assert result.suitability == "Moderate"
    context_service.get_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_context_returns_no_score():
    context_service = AsyncMock()
    context_service.get_context.return_value = make_context(
        actual_source="monthly_forecast",
        available=False,
        resolution="unavailable",
        rainfall_mm=None,
        rainfall_period=None,
        temperature_min_c=None,
        temperature_max_c=None,
        precipitation_probability_max=None,
        missing_targets=["rainfall_mm", "temperature_min_c", "temperature_max_c"],
        message="No valid production-approved monthly forecasts are available.",
    )
    service = WeatherSuitabilityService(context_service)

    result = await service.evaluate(78, date(2026, 11, 15), "hiking")

    assert result.available is False
    assert result.score is None
    assert result.suitability == "Unknown"
    assert result.confidence == "unavailable"
    assert result.weather_source == "monthly_forecast"


@pytest.mark.asyncio
async def test_climatology_is_mapped_without_daily_rain_penalty():
    context_service = AsyncMock()
    context_service.get_context.return_value = make_context(
        travel_date=date(2027, 4, 15),
        actual_source="historical_climatology",
        resolution="calendar_month",
        rainfall_mm=280.58,
        rainfall_period="historical_calendar_month_mean",
        temperature_min_c=25.96,
        temperature_max_c=31.16,
        precipitation_probability_max=None,
    )
    service = WeatherSuitabilityService(context_service)

    result = await service.evaluate(78, date(2027, 4, 15), "beach")

    assert result.available is True
    assert result.score == 100.0
    assert result.weather_source == "historical_climatology"
    assert any("Monthly rainfall" in item for item in result.risk_factors)


@pytest.mark.asyncio
async def test_unknown_activity_is_rejected_before_weather_lookup():
    context_service = AsyncMock()
    service = WeatherSuitabilityService(context_service)

    with pytest.raises(ValueError, match="Unsupported activity type"):
        await service.evaluate(78, TRAVEL_DATE, "skiing")

    context_service.get_context.assert_not_awaited()
