"""OpenWeather 5-day/3-hour client for near-term weather context."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult


class LiveWeatherClient:
    FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
    SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")

    def __init__(self, *, api_key: str | None = None, http_client: httpx.Client | None = None) -> None:
        self._api_key = api_key if api_key is not None else (
            settings.OPENWEATHERMAP_API_KEY or settings.OPENWEATHER_API_KEY
        )
        self._client = http_client or httpx.Client(timeout=15.0)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_forecast(self, *, latitude: float, longitude: float, travel_date: date) -> LiveWeatherResult:
        self._validate_coordinates(latitude, longitude)
        if not self._api_key:
            return self._unavailable(latitude, longitude, travel_date, "OpenWeatherMap API key is not configured.")
        try:
            response = self._client.get(
                self.FORECAST_URL,
                params={"lat": latitude, "lon": longitude, "appid": self._api_key, "units": "metric"},
            )
        except httpx.HTTPError:
            return self._unavailable(latitude, longitude, travel_date, "OpenWeatherMap could not be reached for a live forecast.")
        if response.status_code != httpx.codes.OK:
            return self._unavailable(latitude, longitude, travel_date, f"OpenWeatherMap returned status {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            return self._unavailable(latitude, longitude, travel_date, "OpenWeatherMap returned an invalid forecast response.")
        intervals = payload.get("list") if isinstance(payload, dict) else None
        if not isinstance(intervals, list):
            return self._unavailable(latitude, longitude, travel_date, "OpenWeatherMap returned no usable forecast intervals.")
        selected = [item for item in intervals if self._interval_date(item) == travel_date]
        if not selected:
            return self._unavailable(latitude, longitude, travel_date, "No live forecast intervals are available for the requested date.")

        minimums: list[float] = []
        maximums: list[float] = []
        probabilities: list[float] = []
        descriptions: set[str] = set()
        precipitation = 0.0
        for item in selected:
            main = item.get("main") if isinstance(item.get("main"), dict) else {}
            low = self._number(main.get("temp_min", main.get("temp")))
            high = self._number(main.get("temp_max", main.get("temp")))
            if low is not None:
                minimums.append(low)
            if high is not None:
                maximums.append(high)
            rain = item.get("rain") if isinstance(item.get("rain"), dict) else {}
            precipitation += self._number(rain.get("3h")) or 0.0
            probability = self._number(item.get("pop"))
            if probability is not None:
                probabilities.append(probability)
            weather = item.get("weather")
            if isinstance(weather, list):
                descriptions.update(str(entry["description"]) for entry in weather if isinstance(entry, dict) and entry.get("description"))

        return LiveWeatherResult(
            latitude=latitude,
            longitude=longitude,
            requested_date=travel_date,
            available=True,
            generated_at_utc=datetime.now(timezone.utc),
            forecast=LiveWeatherDay(
                date=travel_date,
                temperature_min_c=min(minimums) if minimums else None,
                temperature_max_c=max(maximums) if maximums else None,
                precipitation_mm_forecast=round(precipitation, 2),
                max_precipitation_probability=max(probabilities) if probabilities else None,
                weather_descriptions=sorted(descriptions),
                forecast_intervals=len(selected),
            ),
            message="Forecast aggregated from available three-hour OpenWeatherMap intervals. A partial day may contain fewer than eight intervals.",
        )

    @classmethod
    def _interval_date(cls, item: Any) -> date | None:
        if not isinstance(item, dict):
            return None
        timestamp = cls._number(item.get("dt"))
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(cls.SRI_LANKA_TIMEZONE).date()
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")

    @staticmethod
    def _unavailable(latitude: float, longitude: float, travel_date: date, message: str) -> LiveWeatherResult:
        return LiveWeatherResult(latitude=latitude, longitude=longitude, requested_date=travel_date, available=False, forecast=None, message=message)
