"""Typed contracts for Stage 8 weather-source routing."""

from __future__ import annotations

from datetime import date, datetime
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


class MonthlyForecastValue(BaseModel):
    target: str
    value: float
    unit: str

    model_name: str
    model_run_id: str

    production_approved: bool


class MonthlyForecastResult(BaseModel):
    district_id: int
    requested_month: date

    available: bool
    source: str = "monthly_forecast"
    resolution: str = "monthly"

    rainfall: MonthlyForecastValue | None = None
    temperature_min: MonthlyForecastValue | None = None
    temperature_max: MonthlyForecastValue | None = None

    missing_targets: list[str] = Field(default_factory=list)

    message: str


class LiveWeatherDay(BaseModel):
    """One Sri Lanka-local calendar day aggregated from 3-hour intervals."""

    date: date
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_mm_forecast: float | None = None
    max_precipitation_probability: float | None = None
    weather_descriptions: list[str] = Field(default_factory=list)
    forecast_intervals: int = 0


class LiveWeatherResult(BaseModel):
    """A short-term OpenWeather forecast response, never stored as training data."""

    latitude: float
    longitude: float
    requested_date: date
    available: bool
    source: str = "openweathermap"
    resolution: str = "three_hourly_aggregated"
    generated_at_utc: datetime | None = None
    forecast: LiveWeatherDay | None = None
    message: str
