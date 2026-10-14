from datetime import date
from unittest.mock import Mock

import pytest

from app.weather_model.context.weather_context_service import (
    WeatherContextService,
)
from app.weather_model.context.schemas import (
    LiveWeatherResult,
    LiveWeatherDay,
    ClimatologyResult,
    ClimatologyValue,
    MonthlyForecastResult,
)


REFERENCE_DATE = date(2026, 10, 11)


@pytest.mark.asyncio
async def test_live_weather_routing():

    live_client = Mock()

    live_client.get_forecast.return_value = LiveWeatherResult(
        latitude=6.0535,
        longitude=80.2210,
        requested_date=date(2026, 10, 13),
        available=True,
        forecast=LiveWeatherDay(
            date=date(2026, 10, 13),
            temperature_min_c=26.38,
            temperature_max_c=30.23,
            precipitation_mm_forecast=7.05,
            max_precipitation_probability=1.0,
            forecast_intervals=8,
        ),
        message="Available",
    )

    service = WeatherContextService(
        live_client=live_client,
    )

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 10, 13),
        latitude=6.0535,
        longitude=80.2210,
        reference_date=REFERENCE_DATE,
    )

    assert result.available is True
    assert result.selected_source == "live_api"
    assert result.rainfall_mm == 7.05
    assert result.provenance["complete_24h_coverage"] is True


@pytest.mark.asyncio
async def test_monthly_unapproved_is_rejected():

    def monthly_lookup(district_id, travel_date):
        return MonthlyForecastResult(
            district_id=district_id,
            requested_month=travel_date.replace(day=1),
            available=False,
            missing_targets=[
                "rainfall_mm",
                "temperature_min_c",
                "temperature_max_c",
            ],
            message="No approved forecast",
        )

    service = WeatherContextService(
        monthly_lookup=monthly_lookup,
    )

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is False
    assert result.selected_source == "monthly_forecast"
    assert result.actual_source == "monthly_forecast"


@pytest.mark.asyncio
async def test_planning_mode_uses_historical_monthly_patterns_before_90_days():
    provider = Mock()
    provider.get_climatology.return_value = ClimatologyResult(
        district_id=78,
        requested_month=date(2026, 11, 1),
        available=True,
        rainfall=ClimatologyValue(
            target="rainfall_mm", mean=250.0, minimum=150.0, maximum=350.0,
            unit="mm/month", observation_years=5, first_year=2021, last_year=2025,
        ),
        message="Historical climatology",
    )
    service = WeatherContextService(climatology_provider=provider)

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=REFERENCE_DATE,
        planning_mode=True,
    )

    assert result.available is True
    assert result.selected_source == "climatology"
    assert result.actual_source == "historical_climatology"
    assert result.rainfall_period == "historical_calendar_month_mean"
    assert result.provenance["planning_mode"] is True
    assert "not a day-specific forecast" in result.message


@pytest.mark.asyncio
async def test_climatology_routing():

    provider = Mock()

    provider.get_climatology.return_value = ClimatologyResult(
        district_id=78,
        requested_month=date(2027, 4, 1),
        available=True,
        rainfall=ClimatologyValue(
            target="rainfall_mm",
            mean=280.58,
            minimum=171.95,
            maximum=395.95,
            standard_deviation=82.876,
            unit="mm/month",
            observation_years=5,
            first_year=2021,
            last_year=2025,
        ),
        message="Historical climatology",
    )

    service = WeatherContextService(
        climatology_provider=provider,
    )

    result = await service.get_context(
        district_id=78,
        travel_date=date(2027, 4, 15),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is True
    assert result.selected_source == "climatology"
    assert result.actual_source == "historical_climatology"
    assert result.rainfall_mm == 280.58
    assert result.rainfall_period == "historical_calendar_month_mean"


@pytest.mark.asyncio
async def test_live_requires_coordinates():

    service = WeatherContextService()

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 10, 13),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is False
    assert result.selected_source == "live_api"


@pytest.mark.asyncio
async def test_past_date_is_not_presented_as_forecast():

    service = WeatherContextService()

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 10, 1),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is False
    assert result.actual_source == "historical"


@pytest.mark.asyncio
async def test_async_monthly_lookup_is_awaited():
    async def monthly_lookup(district_id, travel_date):
        return MonthlyForecastResult(
            district_id=district_id,
            requested_month=travel_date.replace(day=1),
            available=False,
            missing_targets=[
                "rainfall_mm",
                "temperature_min_c",
                "temperature_max_c",
            ],
            message="No approved monthly forecast",
        )

    service = WeatherContextService(monthly_lookup=monthly_lookup)

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is False
    assert result.selected_source == "monthly_forecast"
    assert result.message == "No approved monthly forecast"
