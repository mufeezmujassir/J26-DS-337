"""OpenWeather 5-day/3-hour client for near-term visitor weather context."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.weather_model.context.schemas import LiveWeatherDay, LiveWeatherResult


class LiveWeatherClient:
    """Retrieve and aggregate live forecast intervals without persisting them."""

    FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
    SRI_LANKA_TIMEZONE = ZoneInfo("Asia/Colombo")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else (
            settings.OPENWEATHERMAP_API_KEY or settings.OPENWEATHER_API_KEY
        )
        self._client = http_client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        """Close the internal HTTP client when this instance created it."""
        if self._owns_client:
            self._client.close()

    def get_forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        travel_date: date,
    ) -> LiveWeatherResult:
        """Return only intervals that map to ``travel_date`` in Sri Lanka time."""
        self._validate_coordinates(latitude, longitude)
        if not self._api_key:
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                "OpenWeatherMap API key is not configured.",
            )

        try:
            response = self._client.get(
                self.FORECAST_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "appid": self._api_key,
                    "units": "metric",
                },
            )
        except httpx.HTTPError:
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                "OpenWeatherMap could not be reached for a live forecast.",
            )

        if response.status_code != httpx.codes.OK:
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                f"OpenWeatherMap returned status {response.status_code}.",
            )
        try:
            payload = response.json()
        except ValueError:
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                "OpenWeatherMap returned an invalid forecast response.",
            )

        intervals = payload.get("list") if isinstance(payload, dict) else None
        if not isinstance(intervals, list):
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                "OpenWeatherMap returned no usable forecast intervals.",
            )

        selected = [
            interval
            for interval in intervals
            if self._interval_date(interval) == travel_date
        ]
        if not selected:
            return self._unavailable(
                latitude,
                longitude,
                travel_date,
                "No live forecast intervals are available for the requested date.",
            )

        minimums: list[float] = []
        maximums: list[float] = []
        precipitation_probabilities: list[float] = []
        descriptions: set[str] = set()
        rainfall = 0.0
        for interval in selected:
            main = interval.get("main") if isinstance(interval.get("main"), dict) else {}
            minimum = self._optional_number(main.get("temp_min", main.get("temp")))
            maximum = self._optional_number(main.get("temp_max", main.get("temp")))
            if minimum is not None:
                minimums.append(minimum)
            if maximum is not None:
                maximums.append(maximum)

            rain = interval.get("rain") if isinstance(interval.get("rain"), dict) else {}
            rainfall += self._optional_number(rain.get("3h")) or 0.0
            probability = self._optional_number(interval.get("pop"))
            if probability is not None:
                precipitation_probabilities.append(probability)
            weather = interval.get("weather")
            if isinstance(weather, list):
                descriptions.update(
                    str(item["description"])
                    for item in weather
                    if isinstance(item, dict) and item.get("description")
                )

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
                precipitation_mm_forecast=round(rainfall, 2),
                max_precipitation_probability=(
                    max(precipitation_probabilities)
                    if precipitation_probabilities
                    else None
                ),
                weather_descriptions=sorted(descriptions),
                forecast_intervals=len(selected),
            ),
            message=(
                "Forecast aggregated from available three-hour OpenWeatherMap "
                "intervals. A partial day may contain fewer than eight intervals."
            ),
        )

    @classmethod
    def _interval_date(cls, interval: Any) -> date | None:
        if not isinstance(interval, dict):
            return None
        timestamp = cls._optional_number(interval.get("dt"))
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
                cls.SRI_LANKA_TIMEZONE
            ).date()
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")

    @staticmethod
    def _unavailable(
        latitude: float,
        longitude: float,
        travel_date: date,
        message: str,
    ) -> LiveWeatherResult:
        return LiveWeatherResult(
            latitude=latitude,
            longitude=longitude,
            requested_date=travel_date,
            available=False,
            forecast=None,
            message=message,
        )
