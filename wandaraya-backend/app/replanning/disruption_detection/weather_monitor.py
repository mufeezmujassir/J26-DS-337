"""OpenWeather weather monitor for disruption detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from app.replanning.disruption_detection.utils import (
    get_env_api_key,
    load_config,
)

LOGGER = logging.getLogger(__name__)

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

STORM_TERMS = frozenset({"thunderstorm", "storm", "extreme", "tornado"})
HEAVY_TERMS = frozenset({"heavy"})
LIGHT_TERMS = frozenset({"light", "drizzle", "shower", "damp"})

#: Rainfall volume thresholds (mm) used to classify intensity.
VOLUME_LIGHT_MAX = 2.5
VOLUME_HEAVY_MIN = 7.6

#: Heuristic rain duration (hours) per intensity class.
RAIN_DURATION_HOURS = {
    "none": 0.0,
    "light": 1.0,
    "heavy": 2.5,
    "storm": 4.0,
}


class WeatherMonitor:
    """Polls OpenWeather current conditions for a given location."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or load_config("config.yaml")
        weather_config = self.config.get("weather", {})
        self.api_key_env = weather_config.get(
            "api_key_env", "OPENWEATHER_API_KEY"
        )
        self.units = weather_config.get("units", "metric")
        self.timeout = weather_config.get("timeout_seconds", 10)
        self.heat_threshold_celsius = weather_config.get(
            "heat_threshold_celsius", 35
        )

    def monitor(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
    ) -> Dict[str, Any]:
        """Fetch and reduce weather conditions to a signal dict."""
        signal = self._empty_signal()
        api_key = get_env_api_key(self.api_key_env)

        if not api_key:
            LOGGER.warning(
                "Weather monitor skipped: %s not set", self.api_key_env
            )
            return signal
        if latitude is None or longitude is None:
            LOGGER.warning("Weather monitor skipped: no location provided")
            return signal

        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": api_key,
            "units": self.units,
        }

        try:
            response = requests.get(
                WEATHER_URL, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            LOGGER.error("Weather API request failed: %s", exc)
            return signal

        LOGGER.debug(
            "Weather API returned payload for %s, %s", latitude, longitude
        )
        return self._parse(payload)

    def _parse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce an OpenWeather payload into the module signal contract."""
        descriptions = payload.get("weather") or [{}]
        description = str(descriptions[0].get("description", "")).lower()

        rain = payload.get("rain") or {}
        volume = float(rain.get("3h", rain.get("1h", 0.0)) or 0.0)

        intensity = self._classify_intensity(description, volume)
        temperature = float(
            (payload.get("main") or {}).get("temp", 0.0) or 0.0
        )
        heat_warning = temperature >= self.heat_threshold_celsius

        LOGGER.info(
            "Weather signal: intensity=%s duration=%.1fh temp=%.1fC heat=%s",
            intensity,
            RAIN_DURATION_HOURS[intensity],
            temperature,
            heat_warning,
        )

        return {
            "rain_duration_hours": RAIN_DURATION_HOURS[intensity],
            "rain_intensity": intensity,
            "temperature_celsius": round(temperature, 1),
            "heat_warning": heat_warning,
        }

    @staticmethod
    def _classify_intensity(description: str, volume: float) -> str:
        """Classify rain intensity from the description and mm volume."""
        if volume >= VOLUME_HEAVY_MIN or any(
            term in description for term in STORM_TERMS
        ):
            return "storm"
        if volume > VOLUME_LIGHT_MAX or any(
            term in description for term in HEAVY_TERMS
        ):
            return "heavy"
        if volume > 0.0 or any(term in description for term in LIGHT_TERMS):
            return "light"
        return "none"

    @staticmethod
    def _empty_signal() -> Dict[str, Any]:
        """Degraded signal returned when the API cannot be reached."""
        return {
            "rain_duration_hours": RAIN_DURATION_HOURS["none"],
            "rain_intensity": "none",
            "temperature_celsius": 0.0,
            "heat_warning": False,
        }