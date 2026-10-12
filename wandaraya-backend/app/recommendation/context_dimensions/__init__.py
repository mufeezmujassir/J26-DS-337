"""Standard adapters for individual context dimensions."""

from app.recommendation.context_dimensions.weather_adapter import (
    WeatherDimensionAdapter,
    WeatherDimensionResult,
)

__all__ = ["WeatherDimensionAdapter", "WeatherDimensionResult"]
"""Typed, independent recommendation-context dimension contracts."""

from app.recommendation.context_dimensions.weather_context_contract import (
    WeatherContextDimension,
    to_weather_context_dimension,
)

__all__ = ["WeatherContextDimension", "to_weather_context_dimension"]
