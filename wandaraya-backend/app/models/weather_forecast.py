"""Persisted monthly predictions belonging to a weather model run."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WeatherForecast(Base):
    """One forecast month and its optional prediction interval."""

    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint("run_id", "forecast_month", name="uq_weather_forecast_run_month"),
        CheckConstraint(
            "lower_bound IS NULL OR lower_bound <= predicted_value",
            name="ck_weather_forecast_lower_bound",
        ),
        CheckConstraint(
            "upper_bound IS NULL OR upper_bound >= predicted_value",
            name="ck_weather_forecast_upper_bound",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("weather_model_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    forecast_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_prediction: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
