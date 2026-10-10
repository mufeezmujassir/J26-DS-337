"""Persisted metadata for reproducible district-weather forecasting runs."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WeatherModelRun(Base):
    """One immutable training run for one district and weather target."""

    __tablename__ = "weather_model_runs"
    __table_args__ = (
        CheckConstraint("training_observations >= 0", name="ck_weather_run_observations"),
        CheckConstraint("forecast_horizon_months > 0", name="ck_weather_run_horizon"),
    )

    run_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id"), nullable=False, index=True
    )
    target: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(60), nullable=False)
    training_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_cutoff: Mapped[date] = mapped_column(Date, nullable=False)
    latest_calendar_month: Mapped[date] = mapped_column(Date, nullable=False)
    latest_observed_month: Mapped[date] = mapped_column(Date, nullable=False)
    latest_month_missing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    training_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    production_approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
