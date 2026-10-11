"""Choose the appropriate weather source for a requested travel date."""

from __future__ import annotations

from datetime import date

from app.weather_model.context.schemas import WeatherSource, WeatherSourceDecision

class WeatherSourceSelector:
    """Route dates only; providers perform retrieval and availability checks."""

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

            message = (
                "Historical weather observations are required "
                "for the requested travel date."
            )

            requires_approval = False

        elif days_ahead <= cls.LIVE_FORECAST_DAYS:

            source = WeatherSource.LIVE_API
            resolution = "daily"

            message = (
                "Short-term weather forecast should be "
                "retrieved from the live weather provider."
            )

            requires_approval = False

        elif days_ahead <= cls.MONTHLY_FORECAST_DAYS:

            source = WeatherSource.MONTHLY_FORECAST
            resolution = "monthly"

            message = (
                "Monthly weather outlook should be retrieved "
                "from an approved forecasting model."
            )

            requires_approval = True

        else:

            source = WeatherSource.CLIMATOLOGY
            resolution = "monthly_climatology"

            message = (
                "Long-range travel planning should use "
                "historical monthly climate patterns."
            )

            requires_approval = False

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
