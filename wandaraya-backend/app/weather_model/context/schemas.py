"""Typed contracts for Stage 8 weather-source routing."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class WeatherSource(str, Enum):
    """The weather data source appropriate for a travel-date window."""

    HISTORICAL = "historical"
    LIVE_API = "live_api"
    MONTHLY_FORECAST = "monthly_forecast"
    CLIMATOLOGY = "climatology"


class WeatherSourceDecision(BaseModel):
    """A routing decision only; it makes no availability claim."""

    district_id: int = Field(gt=0)
    travel_date: date
    reference_date: date
    days_ahead: int
    selected_source: WeatherSource
    forecast_resolution: str
    requires_production_approval: bool
    message: str


class WeatherContextResponse(BaseModel):
    """Future retrieval-layer response for the source selected above."""

    district_id: int = Field(gt=0)
    travel_date: date
    source: WeatherSource
    forecast_resolution: str | None = None
    rainfall_mm_monthly: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    production_approved: bool = False
    available: bool = False
    message: str
