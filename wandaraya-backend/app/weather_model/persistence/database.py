"""Synchronous database access for weather forecast import and diagnostics.

The FastAPI application uses the asynchronous session in :mod:`app.database`.
Administrative imports and one-off verification commands need a synchronous
SQLAlchemy engine, but must still use that same configured database URL.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.config import settings
from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun


@lru_cache(maxsize=1)
def get_weather_engine() -> Engine:
    """Return a reusable synchronous engine for the configured PostgreSQL DB."""
    return create_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
    )


__all__ = ["WeatherForecast", "WeatherModelRun", "get_weather_engine"]
