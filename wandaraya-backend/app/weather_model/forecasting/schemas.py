"""Production-safe response schemas for the forecast reliability engine."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ForecastReliability(BaseModel):
    level: Literal["live_provider", "approved_model", "unavailable"]
    reason: str
    issued_at_utc: datetime | None = None
    horizon_days: int | None = None
    freshness: Literal["current", "not_applicable", "unavailable"]
    validation_status: str
    model_evidence_status: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ReliableForecastResult(BaseModel):
    district_id: int
    target: Literal["rainfall_mm", "temperature_min_c", "temperature_max_c"]
    forecast_month: date
    status: Literal["available", "unavailable"]
    predicted_value: float | None = None
    unit: Literal["millimetres", "celsius"]
    source: Literal["openweathermap", "approved_model"] | None = None
    model_version: str | None = None
    production_approved: bool = False
    reliability: ForecastReliability
