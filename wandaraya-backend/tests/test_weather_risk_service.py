from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import pytest

from app.services.weather_risk_service import (
    WeatherRiskService,
    HEAVY_RAIN_THRESHOLD_MM,
    MODERATE_RAIN_THRESHOLD_MM,
)
from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult


def make_mock_result(
    lat: float,
    lon: float,
    d: date,
    available: bool = True,
    precip_mm: float = 5.0,
    prob: float = 0.3,
    descriptions: list = None,
    msg: str = "OK",
) -> LiveWeatherResult:
    forecast = None
    if available:
        forecast = LiveWeatherDay(
            date=d,
            temperature_min_c=25.0,
            temperature_max_c=31.0,
            precipitation_mm_forecast=precip_mm,
            max_precipitation_probability=prob,
            weather_descriptions=descriptions or ["clear sky"],
            forecast_intervals=8,
        )
    return LiveWeatherResult(
        latitude=lat,
        longitude=lon,
        requested_date=d,
        available=available,
        generated_at_utc=datetime.now(timezone.utc),
        forecast=forecast,
        message=msg,
    )


def test_valid_weather_response_processing():
    """Requirement 5: Valid Weather API responses are processed correctly."""
    mock_client = MagicMock()
    today = date(2026, 10, 18)
    mock_client.get_forecast.return_value = make_mock_result(
        6.9271, 79.8612, today, available=True, precip_mm=60.0, prob=0.9, descriptions=["heavy rain"]
    )

    service = WeatherRiskService(client=mock_client)
    res = service.assess_point_weather(6.9271, 79.8612, travel_date=today)

    assert res.available is True
    assert res.status == "RISK_DETECTED"
    assert res.risk_level == "HIGH"
    assert res.precipitation_mm == 60.0
    assert any("heavy rain" in f.lower() for f in res.risk_factors)


def test_weather_api_timeouts_and_http_errors_handled():
    """Requirement 6: Weather API timeouts and HTTP errors are handled."""
    mock_client = MagicMock()
    today = date(2026, 10, 18)
    # Simulate API failure / unavailable response
    mock_client.get_forecast.return_value = make_mock_result(
        6.9271, 79.8612, today, available=False, msg="OpenWeatherMap could not be reached (HTTP 504 Gateway Timeout)."
    )

    service = WeatherRiskService(client=mock_client)
    res = service.assess_point_weather(6.9271, 79.8612, travel_date=today)

    # Must NOT silently report safe / 0-risk
    assert res.available is False
    assert res.status == "RISK_DATA_UNAVAILABLE"
    assert res.risk_level == "NONE"
    assert "Timeout" in res.error_message or "unavailable" in res.error_message.lower()

    # Also test exception raised by client
    mock_client.get_forecast.side_effect = RuntimeError("Connection dropped")
    res_exc = service.assess_point_weather(7.29, 80.63, travel_date=today)
    assert res_exc.available is False
    assert res_exc.status == "RISK_DATA_UNAVAILABLE"
    assert "error" in res_exc.error_message.lower()


def test_missing_weather_fields_no_fabricated_values():
    """Requirement 7: Missing weather fields do not generate fabricated risk values."""
    mock_client = MagicMock()
    today = date(2026, 10, 18)
    # Result with null precipitation
    mock_client.get_forecast.return_value = LiveWeatherResult(
        latitude=6.9271,
        longitude=79.8612,
        requested_date=today,
        available=True,
        generated_at_utc=datetime.now(timezone.utc),
        forecast=LiveWeatherDay(
            date=today,
            temperature_min_c=None,
            temperature_max_c=None,
            precipitation_mm_forecast=0.0,
            max_precipitation_probability=None,
            weather_descriptions=[],
            forecast_intervals=0,
        ),
        message="Sparse interval data.",
    )

    service = WeatherRiskService(client=mock_client)
    res = service.assess_point_weather(6.9271, 79.8612, travel_date=today)

    assert res.available is True
    assert res.precipitation_mm == 0.0
    assert res.precipitation_prob is None
    assert res.status == "NO_RISK_DETECTED"
    assert res.risk_level == "NONE"


def test_route_weather_partial_assessment():
    """Requirement 9: An incomplete data source produces a partial or unavailable assessment."""
    mock_client = MagicMock()
    today = date(2026, 10, 18)

    # First call succeeds, second fails
    mock_client.get_forecast.side_effect = [
        make_mock_result(6.92, 79.86, today, available=True, precip_mm=30.0), # Moderate rain
        make_mock_result(7.29, 80.63, today, available=False, msg="Rate limit exceeded"),
    ]

    service = WeatherRiskService(client=mock_client)
    route_coords = [(6.92, 79.86), (7.29, 80.63)]
    route_res = service.assess_route_weather(route_coords, travel_date=today)

    assert route_res["status"] == "RISK_ASSESSMENT_PARTIAL"
    assert route_res["points_assessed"] == 1
    assert route_res["points_total"] == 2
    assert "some points were unavailable" in route_res["summary"]


def test_weather_caching_and_ttl():
    mock_client = MagicMock()
    today = date(2026, 10, 18)
    mock_client.get_forecast.return_value = make_mock_result(6.92, 79.86, today, available=True, precip_mm=10.0)

    service = WeatherRiskService(client=mock_client, cache_ttl_seconds=3600.0)
    
    # First query -> calls client
    r1 = service.assess_point_weather(6.92, 79.86, travel_date=today)
    assert r1.cached is False
    assert mock_client.get_forecast.call_count == 1

    # Second query for same point -> cache hit
    r2 = service.assess_point_weather(6.92, 79.86, travel_date=today)
    assert r2.cached is True
    assert mock_client.get_forecast.call_count == 1  # No additional API call!
