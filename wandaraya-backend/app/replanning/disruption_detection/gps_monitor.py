"""GPS location monitor for disruption detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.replanning.disruption_detection.utils import (
    haversine_distance,
    load_config,
    time_diff_minutes,
)

LOGGER = logging.getLogger(__name__)


class GpsMonitor:
    """Tracks deviation from the planned route and schedule."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or load_config("config.yaml")
        gps_config = self.config.get("gps", {})
        self.deviation_threshold_km = gps_config.get(
            "deviation_threshold_km", 5
        )
        self.delay_threshold_minutes = gps_config.get(
            "delay_threshold_minutes", 60
        )

    def monitor(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        scheduled_at: Optional[str] = None,
        actual_at: Optional[str] = None,
        planned_waypoints: Optional[List[Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """Reduce the GPS fix and itinerary into a signal dict."""
        signal = self._empty_signal()

        if latitude is None or longitude is None:
            LOGGER.warning("GPS monitor: no fix available, neutral signal")
            return signal

        waypoints = planned_waypoints or []
        deviation = self._nearest_deviation(latitude, longitude, waypoints)

        signal["gps_deviation_km"] = deviation
        signal["off_route"] = deviation > self.deviation_threshold_km

        if scheduled_at and actual_at:
            try:
                delay = time_diff_minutes(scheduled_at, actual_at)
            except ValueError as exc:
                LOGGER.error("GPS monitor: cannot compare times: %s", exc)
                delay = 0
            signal["time_delay_minutes"] = delay
            signal["running_late"] = delay > self.delay_threshold_minutes

        LOGGER.info(
            "GPS signal: deviation=%.1fkm off_route=%s delay=%dmin "
            "running_late=%s",
            deviation,
            signal["off_route"],
            signal["time_delay_minutes"],
            signal["running_late"],
        )

        return signal

    def _nearest_deviation(
        self,
        latitude: float,
        longitude: float,
        waypoints: List[Dict[str, float]],
    ) -> float:
        """Distance to the nearest planned waypoint, in kilometres."""
        if not waypoints:
            return 0.0

        return min(
            haversine_distance(
                latitude,
                longitude,
                float(waypoint["lat"]),
                float(waypoint["lon"]),
            )
            for waypoint in waypoints
        )

    @staticmethod
    def _empty_signal() -> Dict[str, Any]:
        """Neutral signal used when GPS data is unavailable."""
        return {
            "gps_deviation_km": 0.0,
            "time_delay_minutes": 0,
            "off_route": False,
            "running_late": False,
        }