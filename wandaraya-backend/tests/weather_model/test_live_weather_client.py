from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.weather_model.context.live_weather_client import LiveWeatherClient


def make_client(payload: dict, status_code: int = 200) -> LiveWeatherClient:
    return LiveWeatherClient(
        api_key="test-key",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
        ),
    )


def test_aggregates_three_hour_intervals_for_sri_lanka_day() -> None:
    timestamp = int(datetime(2026, 10, 13, tzinfo=timezone.utc).timestamp())
    payload = {"list": [
        {"dt": timestamp, "main": {"temp_min": 24, "temp_max": 29}, "rain": {"3h": 1.5}, "pop": 0.5, "weather": [{"description": "light rain"}]},
        {"dt": timestamp + 10800, "main": {"temp_min": 25, "temp_max": 30}, "rain": {"3h": 2.5}, "pop": 0.7, "weather": [{"description": "cloudy"}]},
    ]}
    local_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(ZoneInfo("Asia/Colombo")).date()
    result = make_client(payload).get_forecast(latitude=6.0535, longitude=80.221, travel_date=local_date)
    assert result.available is True
    assert result.forecast is not None
    assert result.forecast.temperature_min_c == 24.0
    assert result.forecast.temperature_max_c == 30.0
    assert result.forecast.precipitation_mm_forecast == 4.0
    assert result.forecast.max_precipitation_probability == 0.7
    assert result.forecast.forecast_intervals == 2


def test_missing_forecast_date_returns_unavailable() -> None:
    result = make_client({"list": []}).get_forecast(latitude=6.0535, longitude=80.221, travel_date=date(2026, 11, 15))
    assert result.available is False
    assert result.forecast is None


def test_provider_error_returns_unavailable() -> None:
    result = make_client({"message": "Invalid API key"}, 401).get_forecast(latitude=6.0535, longitude=80.221, travel_date=date(2026, 10, 12))
    assert result.available is False


def test_invalid_coordinates() -> None:
    with pytest.raises(ValueError, match="latitude"):
        make_client({"list": []}).get_forecast(latitude=120, longitude=80.221, travel_date=date(2026, 10, 12))
