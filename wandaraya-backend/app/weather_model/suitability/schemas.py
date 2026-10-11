"""Contracts for the baseline weather-suitability rules."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class WeatherSuitabilityInput(BaseModel):
    district_id: int = Field(gt=0)
    travel_date: date
    activity_type: str
    weather_source: str
    rainfall_mm: float | None = Field(default=None, ge=0)
    rainfall_period: str | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_probability_max: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )


class WeatherSuitabilityResult(BaseModel):
    district_id: int
    travel_date: date
    activity_type: str
    score: float | None = None
    confidence: str
    suitability: str
    weather_source: str
    risk_factors: list[str] = Field(default_factory=list)
    explanation: str


class IntegratedSuitabilityResponse(BaseModel):
    """Suitability score together with the weather context that produced it."""

    district_id: int
    travel_date: date
    activity_type: str
    available: bool
    score: float | None = None
    suitability: str
    confidence: str
    weather_source: str
    weather_resolution: str
    rainfall_mm: float | None = None
    rainfall_period: str | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    risk_factors: list[str] = Field(default_factory=list)
    missing_targets: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    explanation: str
