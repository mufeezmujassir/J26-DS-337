"""Choose a weather-data source from the requested travel-date window."""

from __future__ import annotations

from datetime import date

from app.weather_model.context.schemas import WeatherSource, WeatherSourceDecision


class WeatherSourceSelector:
    """Route dates only; providers handle retrieval and availability."""

    LIVE_FORECAST_DAYS = 5
    MONTHLY_FORECAST_DAYS = 90

    @classmethod
    def select(
        cls,
        district_id: int,
        travel_date: date,
        reference_date: date | None = None,
    ) -> WeatherSourceDecision:
        if district_id <= 0:
            raise ValueError("district_id must be positive")

        today = reference_date or date.today()
        days_ahead = (travel_date - today).days

        if days_ahead < 0:
            source = WeatherSource.HISTORICAL
            resolution = "historical"
            requires_approval = False
            message = "Historical weather observations are required for the requested travel date."
        elif days_ahead <= cls.LIVE_FORECAST_DAYS:
            source = WeatherSource.LIVE_API
            resolution = "daily"
            requires_approval = False
            message = "Short-term weather forecast should be retrieved from the live weather provider."
        elif days_ahead <= cls.MONTHLY_FORECAST_DAYS:
            source = WeatherSource.MONTHLY_FORECAST
            resolution = "monthly"
            requires_approval = True
            message = "Monthly weather outlook should be retrieved from an approved forecasting model."
        else:
            source = WeatherSource.CLIMATOLOGY
            resolution = "monthly_climatology"
            requires_approval = False
            message = "Long-range travel planning should use historical monthly climate patterns."

        return WeatherSourceDecision(
            district_id=district_id,
            travel_date=travel_date,
            reference_date=today,
            days_ahead=days_ahead,
            selected_source=source,
            forecast_resolution=resolution,
            requires_production_approval=requires_approval,
            message=message,
        )
