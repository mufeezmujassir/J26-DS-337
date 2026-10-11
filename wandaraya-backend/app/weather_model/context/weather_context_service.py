from datetime import date
from inspect import isawaitable
from typing import Callable

from starlette.concurrency import run_in_threadpool

from app.weather_model.context.schemas import (
    UnifiedWeatherContext,
    WeatherSource,
)
from app.weather_model.context.source_selector import (
    WeatherSourceSelector,
)
from app.weather_model.context.live_weather_client import (
    LiveWeatherClient,
)
from app.weather_model.context.climatology_provider import (
    ClimatologyProvider,
)


class WeatherContextService:

    def __init__(
        self,
        live_client: LiveWeatherClient | None = None,
        climatology_provider: ClimatologyProvider | None = None,
        monthly_lookup: Callable | None = None,
    ):
        self.live_client = live_client or LiveWeatherClient()

        self.climatology_provider = (
            climatology_provider or ClimatologyProvider()
        )

        # Function signature:
        # monthly_lookup(district_id, travel_date)
        # Must return the existing MonthlyForecastResult.
        self.monthly_lookup = monthly_lookup

    async def get_context(
        self,
        district_id: int,
        travel_date: date,
        latitude: float | None = None,
        longitude: float | None = None,
        reference_date: date | None = None,
    ) -> UnifiedWeatherContext:

        decision = WeatherSourceSelector.select(
            district_id=district_id,
            travel_date=travel_date,
            reference_date=reference_date,
        )

        common = {
            "district_id": district_id,
            "travel_date": travel_date,
            "reference_date": decision.reference_date,
            "days_ahead": decision.days_ahead,
            "selected_source": decision.selected_source.value,
            "latitude": latitude,
            "longitude": longitude,
        }

        if decision.selected_source == WeatherSource.LIVE_API:

            if (latitude is None) != (longitude is None):
                raise ValueError(
                    "Latitude and longitude must be supplied together."
                )

            if latitude is None:
                return self._unavailable(
                    common,
                    "live_api",
                    "Exact coordinates are required for live weather.",
                )

            # LiveWeatherClient deliberately uses a synchronous httpx client.
            # Keep that I/O off FastAPI's event loop.
            result = await run_in_threadpool(
                self.live_client.get_forecast,
                latitude=latitude,
                longitude=longitude,
                travel_date=travel_date,
            )

            if not result.available or result.forecast is None:
                return self._unavailable(
                    common,
                    "live_api",
                    result.message,
                )

            forecast = result.forecast

            return UnifiedWeatherContext(
                **common,
                actual_source=result.source,
                available=True,
                resolution=result.resolution,
                rainfall_mm=forecast.precipitation_mm_forecast,
                rainfall_period="available_3h_intervals",
                temperature_min_c=forecast.temperature_min_c,
                temperature_max_c=forecast.temperature_max_c,
                precipitation_probability_max=(
                    forecast.max_precipitation_probability
                ),
                provenance={
                    "provider": "OpenWeatherMap",
                    "generated_at_utc": (
                        result.generated_at_utc.isoformat()
                        if result.generated_at_utc
                        else None
                    ),
                    "forecast_intervals": (
                        forecast.forecast_intervals
                    ),
                    "complete_24h_coverage": (
                        forecast.forecast_intervals == 8
                    ),
                    "weather_descriptions": (
                        forecast.weather_descriptions
                    ),
                },
                message=result.message,
            )

        if decision.selected_source == WeatherSource.MONTHLY_FORECAST:

            if self.monthly_lookup is None:
                return self._unavailable(
                    common,
                    "monthly_forecast",
                    "Monthly forecast provider is not connected.",
                )

            result = self.monthly_lookup(
                district_id,
                travel_date,
            )

            # Test doubles may be synchronous, while the real PostgreSQL
            # provider is asynchronous and needs the request AsyncSession.
            if isawaitable(result):
                result = await result

            if not result.available:
                return self._unavailable(
                    common,
                    "monthly_forecast",
                    result.message,
                    missing_targets=result.missing_targets,
                )

            # Defense in depth: the existing Stage 8.2 provider
            # must also filter production-approved runs in SQL.
            for item in (
                result.rainfall,
                result.temperature_min,
                result.temperature_max,
            ):
                if item is not None and not item.production_approved:
                    return self._unavailable(
                        common,
                        "monthly_forecast",
                        "An unapproved model result was rejected.",
                    )

            return UnifiedWeatherContext(
                **common,
                actual_source=result.source,
                available=True,
                resolution=result.resolution,
                rainfall_mm=(
                    result.rainfall.value
                    if result.rainfall else None
                ),
                rainfall_period="calendar_month",
                temperature_min_c=(
                    result.temperature_min.value
                    if result.temperature_min else None
                ),
                temperature_max_c=(
                    result.temperature_max.value
                    if result.temperature_max else None
                ),
                missing_targets=result.missing_targets,
                provenance={
                    "requested_month": (
                        result.requested_month.isoformat()
                    ),
                    "model_runs": {
                        key: item.model_run_id
                        for key, item in {
                            "rainfall": result.rainfall,
                            "temperature_min": result.temperature_min,
                            "temperature_max": result.temperature_max,
                        }.items()
                        if item is not None
                    },
                    "production_approved": True,
                },
                message=result.message,
            )

        if decision.selected_source == WeatherSource.CLIMATOLOGY:

            # Pandas CSV processing is synchronous, so avoid blocking the
            # event loop when this route is served by FastAPI.
            result = await run_in_threadpool(
                self.climatology_provider.get_climatology,
                district_id=district_id,
                travel_date=travel_date,
            )

            if not result.available:
                return self._unavailable(
                    common,
                    "historical_climatology",
                    result.message,
                    missing_targets=result.missing_targets,
                )

            return UnifiedWeatherContext(
                **common,
                actual_source=result.source,
                available=True,
                resolution=result.resolution,
                rainfall_mm=(
                    result.rainfall.mean
                    if result.rainfall else None
                ),
                rainfall_period="historical_calendar_month_mean",
                temperature_min_c=(
                    result.temperature_min.mean
                    if result.temperature_min else None
                ),
                temperature_max_c=(
                    result.temperature_max.mean
                    if result.temperature_max else None
                ),
                missing_targets=result.missing_targets,
                provenance={
                    "dataset": "district_monthly_observations",
                    "rainfall_observation_years": (
                        result.rainfall.observation_years
                        if result.rainfall else None
                    ),
                    "temperature_min_observation_years": (
                        result.temperature_min.observation_years
                        if result.temperature_min else None
                    ),
                    "temperature_max_observation_years": (
                        result.temperature_max.observation_years
                        if result.temperature_max else None
                    ),
                    "is_daily_forecast": False,
                },
                message=result.message,
            )

        return self._unavailable(
            common,
            "historical",
            "Historical date-specific weather lookup is not implemented.",
        )

    @staticmethod
    def _unavailable(
        common: dict,
        source: str,
        message: str,
        missing_targets: list[str] | None = None,
    ) -> UnifiedWeatherContext:

        return UnifiedWeatherContext(
            **common,
            actual_source=source,
            available=False,
            resolution="unavailable",
            missing_targets=missing_targets or [],
            message=message,
        )
