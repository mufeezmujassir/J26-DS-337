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
    DailyForecastResult,
    DailyForecastValue,
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
async def test_daily_model_unavailable_is_reported():

    provider = Mock()
    provider.get_daily_forecast.return_value = DailyForecastResult(
            district_id=78,
            requested_date=date(2026, 11, 15),
            available=False,
            missing_targets=[
                "rainfall_mm",
                "temperature_min_c",
                "temperature_max_c",
            ],
            message="No approved forecast",
        )

    service = WeatherContextService(daily_forecast_provider=provider)

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is False
    assert result.selected_source == "daily_forecast"
    assert result.actual_source == "nasa_power_daily_prophet"


@pytest.mark.asyncio
async def test_planning_mode_still_uses_date_specific_daily_model():
    provider = Mock()
    provider.get_daily_forecast.return_value = DailyForecastResult(
        district_id=78,
        requested_date=date(2026, 11, 15),
        available=True,
        rainfall=DailyForecastValue(
            target="rainfall_mm", value=8.0, lower=0.0, upper=30.0, unit="mm/day",
        ),
        message="Daily Prophet estimate",
    )
    service = WeatherContextService(daily_forecast_provider=provider)

    result = await service.get_context(
        district_id=78,
        travel_date=date(2026, 11, 15),
        reference_date=REFERENCE_DATE,
        planning_mode=True,
    )

    assert result.available is True
    assert result.selected_source == "daily_forecast"
    assert result.actual_source == "nasa_power_daily_prophet"
    assert result.rainfall_period == "daily"
    assert result.rainfall_mm == 8.0


@pytest.mark.asyncio
async def test_long_range_daily_routing():

    provider = Mock()

    provider.get_daily_forecast.return_value = DailyForecastResult(
        district_id=78,
        requested_date=date(2027, 4, 15),
        available=True,
        rainfall=DailyForecastValue(
            target="rainfall_mm", value=12.5, lower=0.0, upper=42.0, unit="mm/day",
        ),
        message="Daily Prophet estimate",
    )

    service = WeatherContextService(
        daily_forecast_provider=provider,
    )

    result = await service.get_context(
        district_id=78,
        travel_date=date(2027, 4, 15),
        reference_date=REFERENCE_DATE,
    )

    assert result.available is True
    assert result.selected_source == "daily_forecast"
    assert result.actual_source == "nasa_power_daily_prophet"
    assert result.rainfall_mm == 12.5
    assert result.rainfall_period == "daily"


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
async def test_legacy_async_monthly_lookup_remains_supported_directly():
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

    assert service.monthly_lookup is monthly_lookup
