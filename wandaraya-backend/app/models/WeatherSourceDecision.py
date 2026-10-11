"""Deprecated compatibility import for the moved Stage 8 schemas.

Weather context schemas belong in ``app.weather_model.context``.  This module
keeps older imports working without defining database models here.
"""

from app.weather_model.context.schemas import (
    WeatherContextResponse,
    WeatherSource,
    WeatherSourceDecision,
)

__all__ = ["WeatherContextResponse", "WeatherSource", "WeatherSourceDecision"]
