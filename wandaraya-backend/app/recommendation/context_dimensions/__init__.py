"""Standard adapters for individual context dimensions."""

from app.recommendation.context_dimensions.weather_adapter import (
    WeatherDimensionAdapter,
    WeatherDimensionResult,
)

__all__ = ["WeatherDimensionAdapter", "WeatherDimensionResult"]
