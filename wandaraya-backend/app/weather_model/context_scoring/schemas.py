"""Pure contracts for attraction-level weather context scoring."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class WeatherConditions(BaseModel):
    status: Literal["available", "unavailable"]
    source: str | None = None
    resolution: Literal["daily", "three_hourly_aggregated", "monthly"] | None = None
    reliability_level: Literal["live_provider", "approved_model", "unavailable"] = "unavailable"
    issued_at_utc: datetime | None = None
    rainfall_mm: float | None = Field(default=None, ge=0)
    rainfall_period: Literal["daily", "available_3h_intervals", "monthly_total"] | None = None
    precipitation_probability: float | None = Field(default=None, ge=0, le=1)
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None


class AttractionWeatherRequest(BaseModel):
    attraction_id: int
    activity: str
    travel_date: date
    weather: WeatherConditions


class ScoreExplanation(BaseModel):
    factor: str
    effect: Literal["penalty", "informational"]
    detail: str
    score_delta: float | None = None


class AttractionWeatherScore(BaseModel):
    attraction_id: int
    activity: str
    travel_date: date
    status: Literal["available", "unknown"]
    suitability_score: float | None = Field(default=None, ge=0, le=1)
    suitability_level: Literal["excellent", "good", "moderate", "poor", "unknown"]
    forecast_source: str | None = None
    weather_resolution: str | None = None
    explanation: str
    factors: list[ScoreExplanation] = Field(default_factory=list)
    reliability_level: str
