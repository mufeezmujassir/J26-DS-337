from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.weather_model.context.live_weather_client import LiveWeatherClient


def make_client(payload: dict, status_code: int = 200) -> LiveWeatherClient:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, json=payload)
    )
    return LiveWeatherClient(
        api_key="test-key",
        http_client=httpx.Client(transport=transport),
    )


def test_aggregates_three_hour_intervals_for_sri_lanka_day() -> None:
    first_timestamp = int(datetime(2026, 10, 13, 0, tzinfo=timezone.utc).timestamp())
    payload = {
        "list": [
            {
                "dt": first_timestamp,
                "main": {"temp_min": 24.0, "temp_max": 29.0},
                "rain": {"3h": 1.5},
                "pop": 0.5,
                "weather": [{"description": "light rain"}],
            },
            {
                "dt": first_timestamp + 3 * 60 * 60,
                "main": {"temp_min": 25.0, "temp_max": 30.0},
                "rain": {"3h": 2.5},
                "pop": 0.7,
                "weather": [{"description": "cloudy"}],
            },
        ]
    }
    local_date = datetime.fromtimestamp(first_timestamp, tz=timezone.utc).astimezone(
        ZoneInfo("Asia/Colombo")
    ).date()
    result = make_client(payload).get_forecast(
        latitude=6.0535,
        longitude=80.2210,
        travel_date=local_date,
    )

    assert result.available is True
    assert result.forecast is not None
    assert result.forecast.temperature_min_c == 24.0
    assert result.forecast.temperature_max_c == 30.0
    assert result.forecast.precipitation_mm_forecast == 4.0
    assert result.forecast.max_precipitation_probability == 0.7
    assert result.forecast.forecast_intervals == 2


def test_missing_forecast_date_returns_unavailable() -> None:
    result = make_client({"list": []}).get_forecast(
        latitude=6.0535,
        longitude=80.2210,
        travel_date=date(2026, 11, 15),
    )

    assert result.available is False
    assert result.forecast is None


def test_provider_error_returns_unavailable() -> None:
    result = make_client({"message": "Invalid API key"}, status_code=401).get_forecast(
        latitude=6.0535,
        longitude=80.2210,
        travel_date=date(2026, 10, 12),
    )

    assert result.available is False
    assert result.forecast is None


def test_invalid_coordinates() -> None:
    client = make_client({"list": []})
    with pytest.raises(ValueError, match="latitude"):
        client.get_forecast(
            latitude=120.0,
            longitude=80.0,
            travel_date=date(2026, 10, 12),
        )
