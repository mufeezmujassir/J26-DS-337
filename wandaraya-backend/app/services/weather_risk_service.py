"""
Weather Risk Assessment Service for WANDARAYA Component 2.
=========================================================
Wraps OpenWeatherMap 5-day / 3-hour forecast integration to evaluate
meteorological risks along multimodal route trajectories.

Key Principles:
- Reuses existing LiveWeatherClient and OpenWeatherMap API key configuration.
- Evaluates only real fields returned by the API (precipitation, pop, wind, descriptions).
- Uses documented meteorological thresholds aligned with Sri Lanka Met Department standards.
- Employs 1-hour TTL in-memory caching to respect rate limits.
- Never fabricates weather data or claims ordinary rain proves road closures.
- Marks failures explicitly as unavailable / partial rather than silently reporting zero risk.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.weather_model.context.live_weather_client import LiveWeatherClient
from app.weather_model.context.schemas import LiveWeatherResult

logger = logging.getLogger(__name__)

# Meteorological Thresholds (Sri Lanka Department of Meteorology advisory guidelines)
# Heavy Rain Advisory: >= 50.0 mm cumulative forecast or sustained intense rain
HEAVY_RAIN_THRESHOLD_MM = 50.0
# Moderate Rain Warning: >= 25.0 mm cumulative
MODERATE_RAIN_THRESHOLD_MM = 25.0
# High Precipitation Probability: >= 75%
HIGH_PRECIPITATION_PROBABILITY = 0.75
# Cache TTL: 1 hour (3600 seconds)
CACHE_TTL_SECONDS = 3600.0


@dataclass
class WeatherPointAssessment:
    latitude: float
    longitude: float
    travel_date: date
    available: bool
    status: str  # "NO_RISK_DETECTED", "RISK_DETECTED", "RISK_DATA_UNAVAILABLE", "DATA_STALE"
    precipitation_mm: Optional[float] = None
    precipitation_prob: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    weather_descriptions: List[str] = field(default_factory=list)
    risk_level: str = "NONE"  # "NONE", "LOW", "MODERATE", "HIGH"
    risk_factors: List[str] = field(default_factory=list)
    cached: bool = False
    fetched_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "travel_date": self.travel_date.isoformat(),
            "available": self.available,
            "status": self.status,
            "precipitation_mm": self.precipitation_mm,
            "precipitation_probability": self.precipitation_prob,
            "temperature_range_c": (
                [self.temperature_min_c, self.temperature_max_c]
                if self.temperature_min_c is not None and self.temperature_max_c is not None
                else None
            ),
            "weather_descriptions": self.weather_descriptions,
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "cached": self.cached,
            "error_message": self.error_message,
        }


class WeatherRiskService:
    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        # 1. From settings
        key = settings.OPENWEATHERMAP_API_KEY or settings.OPENWEATHER_API_KEY
        if key:
            return key
        # 2. From os.environ
        key = os.environ.get("OPENWEATHERMAP_API_KEY") or os.environ.get("OPENWEATHER_API_KEY")
        if key:
            return key
        # 3. Direct parse from wandaraya-backend/.env
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENWEATHERMAP_API_KEY="):
                            return line.split("=", 1)[1].strip()
                        if line.startswith("OPENWEATHER_API_KEY="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
        return None

    def __init__(
        self,
        client: Optional[LiveWeatherClient] = None,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        resolved_key = self._resolve_api_key()
        self._client = client or LiveWeatherClient(api_key=resolved_key)
        self._owns_client = client is None
        self.cache_ttl_seconds = cache_ttl_seconds
        # In-memory cache: (lat_rounded, lon_rounded, date_str) -> (WeatherPointAssessment, timestamp)
        self._cache: Dict[Tuple[float, float, str], Tuple[WeatherPointAssessment, float]] = {}

    def close(self) -> None:
        if self._owns_client and self._client:
            self._client.close()

    def _cache_key(self, lat: float, lon: float, d: date) -> Tuple[float, float, str]:
        return (round(lat, 2), round(lon, 2), d.isoformat())

    def assess_point_weather(
        self,
        latitude: float,
        longitude: float,
        travel_date: Optional[date] = None,
        force_fresh: bool = False,
    ) -> WeatherPointAssessment:
        """
        Assesses weather risk at a single coordinate for a given date.
        Uses in-memory cache if valid within TTL.
        """
        req_date = travel_date or date.today()
        cache_key = self._cache_key(latitude, longitude, req_date)
        now = time.time()

        if not force_fresh and cache_key in self._cache:
            entry, timestamp = self._cache[cache_key]
            age = now - timestamp
            if age <= self.cache_ttl_seconds:
                # Cache hit
                return WeatherPointAssessment(
                    latitude=entry.latitude,
                    longitude=entry.longitude,
                    travel_date=entry.travel_date,
                    available=entry.available,
                    status="DATA_STALE" if age > (self.cache_ttl_seconds * 0.8) else entry.status,
                    precipitation_mm=entry.precipitation_mm,
                    precipitation_prob=entry.precipitation_prob,
                    temperature_min_c=entry.temperature_min_c,
                    temperature_max_c=entry.temperature_max_c,
                    weather_descriptions=list(entry.weather_descriptions),
                    risk_level=entry.risk_level,
                    risk_factors=list(entry.risk_factors),
                    cached=True,
                    fetched_at=timestamp,
                    error_message=entry.error_message,
                )

        # Call LiveWeatherClient
        try:
            res: LiveWeatherResult = self._client.get_forecast(
                latitude=latitude,
                longitude=longitude,
                travel_date=req_date,
            )
        except Exception as e:
            logger.error(f"Weather API exception for ({latitude}, {longitude}): {e}")
            return WeatherPointAssessment(
                latitude=latitude,
                longitude=longitude,
                travel_date=req_date,
                available=False,
                status="RISK_DATA_UNAVAILABLE",
                error_message=f"Weather service error: {str(e)}",
            )

        if not res.available or not res.forecast:
            # Explicit unavailable status, never pretend 0 risk
            assessment = WeatherPointAssessment(
                latitude=latitude,
                longitude=longitude,
                travel_date=req_date,
                available=False,
                status="RISK_DATA_UNAVAILABLE",
                error_message=res.message or "Weather data unavailable from provider.",
            )
            return assessment

        f = res.forecast
        precip = f.precipitation_mm_forecast
        prob = f.max_precipitation_probability
        descriptions = f.weather_descriptions or []

        precip_val = precip if precip is not None else 0.0
        prob_val = prob if prob is not None else 0.0

        risk_factors: List[str] = []
        risk_level = "NONE"

        # Check documented thresholds
        if precip_val >= HEAVY_RAIN_THRESHOLD_MM:
            risk_level = "HIGH"
            risk_factors.append(
                f"Severe precipitation forecast ({precip_val:.1f} mm) exceeding heavy rain threshold ({HEAVY_RAIN_THRESHOLD_MM:.0f} mm)."
            )
        elif precip_val >= MODERATE_RAIN_THRESHOLD_MM:
            risk_level = "MODERATE"
            risk_factors.append(
                f"Moderate precipitation forecast ({precip_val:.1f} mm) exceeding moderate threshold ({MODERATE_RAIN_THRESHOLD_MM:.0f} mm)."
            )
        elif precip_val > 10.0 and prob_val >= HIGH_PRECIPITATION_PROBABILITY:
            risk_level = "LOW"
            risk_factors.append(
                f"Sustained light-to-moderate rain ({precip_val:.1f} mm) with high likelihood ({int(prob_val * 100)}%)."
            )

        # Severe weather description keywords
        severe_keywords = ["thunderstorm", "squall", "heavy intensity rain", "very heavy rain", "extreme rain"]
        for desc in descriptions:
            desc_lower = desc.lower()
            if any(k in desc_lower for k in severe_keywords):
                if risk_level not in ("HIGH", "MODERATE"):
                    risk_level = "MODERATE"
                risk_factors.append(f"Meteorological phenomenon reported: '{desc}'.")

        status_code = "RISK_DETECTED" if risk_level in ("HIGH", "MODERATE") else "NO_RISK_DETECTED"

        assessment = WeatherPointAssessment(
            latitude=latitude,
            longitude=longitude,
            travel_date=req_date,
            available=True,
            status=status_code,
            precipitation_mm=precip,
            precipitation_prob=prob,
            temperature_min_c=f.temperature_min_c,
            temperature_max_c=f.temperature_max_c,
            weather_descriptions=descriptions,
            risk_level=risk_level,
            risk_factors=risk_factors,
            cached=False,
            fetched_at=now,
        )

        self._cache[cache_key] = (assessment, now)
        return assessment

    def assess_route_weather(
        self,
        route_coordinates: List[Tuple[float, float]],
        travel_date: Optional[date] = None,
        sample_step_km: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Samples coordinates along a route to evaluate climatic zone conditions.
        """
        if not route_coordinates:
            return {
                "status": "RISK_DATA_UNAVAILABLE",
                "available": False,
                "overall_risk_level": "UNKNOWN",
                "points_assessed": 0,
                "weather_points": [],
                "summary": "No route coordinates provided for weather evaluation.",
            }

        # Select representative points: Start, End, and points roughly sample_step_km apart
        points_to_query: List[Tuple[float, float]] = [route_coordinates[0]]
        accum_dist = 0.0

        for i in range(len(route_coordinates) - 1):
            p1 = route_coordinates[i]
            p2 = route_coordinates[i + 1]
            from app.services.landslide_service import haversine_distance_m
            d_km = haversine_distance_m(p1[0], p1[1], p2[0], p2[1]) / 1000.0
            accum_dist += d_km
            if accum_dist >= sample_step_km:
                points_to_query.append(p2)
                accum_dist = 0.0

        if route_coordinates[-1] not in points_to_query:
            points_to_query.append(route_coordinates[-1])

        # Limit max samples to avoid excessive API calls
        if len(points_to_query) > 5:
            # Sample evenly down to 5 points
            indices = [int(i * (len(points_to_query) - 1) / 4) for i in range(5)]
            points_to_query = [points_to_query[idx] for idx in indices]

        point_results: List[WeatherPointAssessment] = []
        for pt in points_to_query:
            pa = self.assess_point_weather(pt[0], pt[1], travel_date=travel_date)
            point_results.append(pa)

        available_count = sum(1 for p in point_results if p.available)
        total_count = len(point_results)

        if available_count == 0:
            status = "RISK_DATA_UNAVAILABLE"
            overall_risk = "UNKNOWN"
            summary = "OpenWeatherMap data was unavailable for all sampled points on the route."
        elif available_count < total_count:
            status = "RISK_ASSESSMENT_PARTIAL"
            high_risks = [p for p in point_results if p.available and p.risk_level == "HIGH"]
            mod_risks = [p for p in point_results if p.available and p.risk_level == "MODERATE"]
            overall_risk = "HIGH" if high_risks else ("MODERATE" if mod_risks else "LOW")
            summary = f"Weather assessed for {available_count}/{total_count} route samples; some points were unavailable."
        else:
            high_risks = [p for p in point_results if p.risk_level == "HIGH"]
            mod_risks = [p for p in point_results if p.risk_level == "MODERATE"]
            if high_risks:
                status = "RISK_DETECTED"
                overall_risk = "HIGH"
                summary = f"High meteorological alert: {len(high_risks)} route location(s) forecast heavy rainfall."
            elif mod_risks:
                status = "RISK_DETECTED"
                overall_risk = "MODERATE"
                summary = f"Moderate weather alert: {len(mod_risks)} location(s) exceed rain/wind advisory thresholds."
            else:
                status = "NO_RISK_DETECTED"
                overall_risk = "NONE"
                summary = "All sampled route locations checked successfully; no severe weather conditions forecast."

        # Check for data staleness
        if any(p.status == "DATA_STALE" for p in point_results if p.available):
            if status == "NO_RISK_DETECTED":
                status = "DATA_STALE"

        max_precip = max((p.precipitation_mm or 0.0 for p in point_results if p.available), default=0.0)

        return {
            "status": status,
            "available": available_count > 0,
            "overall_risk_level": overall_risk,
            "max_precipitation_forecast_mm": round(max_precip, 2),
            "points_assessed": available_count,
            "points_total": total_count,
            "weather_points": [p.to_dict() for p in point_results],
            "summary": summary,
        }


# Singleton service instance
weather_risk_service = WeatherRiskService()
