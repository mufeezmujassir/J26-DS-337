"""Retrieve exact-month, production-approved Stage 7 forecasts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun
from app.weather_model.context.schemas import MonthlyForecastResult, MonthlyForecastValue
from app.weather_model.forecasting.forecast_service import ForecastService
from app.weather_model.forecasting.reliability import ArtifactVerifier, is_forecast_after_training_cutoff


class MonthlyForecastProvider:
    TARGETS = ("rainfall_mm", "temperature_min_c", "temperature_max_c")
    _FIELDS = {
        "rainfall_mm": "rainfall",
        "temperature_min_c": "temperature_min",
        "temperature_max_c": "temperature_max",
    }
    _UNITS = {"rainfall_mm": "mm/month", "temperature_min_c": "°C", "temperature_max_c": "°C"}
    REGISTRY_PATH = Path("data/weather/reports/registry/weather_model_registry.json")

    @classmethod
    async def get_monthly_forecast(
        cls, db: AsyncSession, *, district_id: int, travel_date: date
    ) -> MonthlyForecastResult:
        if district_id <= 0:
            raise ValueError("district_id must be positive")
        requested_month = travel_date.replace(day=1)
        statement = (
            select(WeatherModelRun, WeatherForecast)
            .join(WeatherForecast, WeatherForecast.run_id == WeatherModelRun.run_id)
            .where(
                WeatherModelRun.district_id == district_id,
                WeatherModelRun.production_approved.is_(True),
                WeatherModelRun.target.in_(cls.TARGETS),
                WeatherForecast.forecast_month == requested_month,
            )
            .order_by(
                WeatherModelRun.target,
                WeatherModelRun.created_at_utc.desc(),
                WeatherForecast.created_at.desc(),
                WeatherModelRun.run_id.desc(),
            )
        )
        result = cls._build_result(district_id, requested_month, (await db.execute(statement)).all())
        if result.missing_targets:
            cls._fill_from_approved_artifacts(result)
        return result

    @classmethod
    def _fill_from_approved_artifacts(cls, result: MonthlyForecastResult) -> None:
        """Fill absent exact-month rows from checksum-verified approved artifacts.

        This keeps arbitrary future months available without pre-populating an
        unbounded forecast table. Candidate or unapproved artifacts still fail
        closed through ``ArtifactVerifier``.
        """
        verifier = ArtifactVerifier(cls.REGISTRY_PATH)
        for target in list(result.missing_targets):
            try:
                artifact = verifier.verify(result.district_id, target)
                if not is_forecast_after_training_cutoff(artifact, result.requested_month):
                    continue
                value = ForecastService._predict_from_artifact(artifact, result.requested_month)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                continue
            setattr(result, cls._FIELDS[target], MonthlyForecastValue(
                target=target,
                value=float(value),
                unit=cls._UNITS[target],
                model_name=artifact.model_name,
                model_run_id=f"artifact:{artifact.model_version}",
                production_approved=True,
            ))
        result.missing_targets = [
            target for target in cls.TARGETS
            if getattr(result, cls._FIELDS[target]) is None
        ]
        result.available = len(result.missing_targets) < len(cls.TARGETS)
        if result.available and not result.missing_targets:
            result.message = "Production-approved monthly forecast data is available for the requested month."
        elif result.available:
            result.message = "Partial production-approved monthly forecast data is available for the requested month."

    @classmethod
    def _build_result(
        cls,
        district_id: int,
        requested_month: date,
        rows: Iterable[tuple[WeatherModelRun, WeatherForecast]],
    ) -> MonthlyForecastResult:
        selected: dict[str, MonthlyForecastValue] = {}
        for run, forecast in rows:
            if run.target in selected or not cls._is_valid(run, forecast, requested_month):
                continue
            selected[run.target] = MonthlyForecastValue(
                target=run.target,
                value=float(forecast.predicted_value),
                unit=cls._UNITS[run.target],
                model_name=run.model_name,
                model_run_id=run.run_id,
                production_approved=True,
            )

        missing = [target for target in cls.TARGETS if target not in selected]
        available = bool(selected)
        result = MonthlyForecastResult(
            district_id=district_id,
            requested_month=requested_month,
            available=available,
            missing_targets=missing,
            message=(
                "Monthly forecast data is available for the requested month."
                if available and not missing
                else "Partial production-approved monthly forecast data is available for the requested month."
                if available
                else "No valid production-approved monthly forecasts are available for the requested month."
            ),
        )
        for target, value in selected.items():
            setattr(result, cls._FIELDS[target], value)
        return result

    @classmethod
    def _is_valid(cls, run: WeatherModelRun, forecast: WeatherForecast, month: date) -> bool:
        if (
            not run.production_approved
            or run.target not in cls.TARGETS
            or run.run_id != forecast.run_id
            or forecast.forecast_month != month
            or forecast.predicted_value is None
            or run.training_cutoff >= month
        ):
            return False
        if cls._utc_naive(forecast.created_at) < cls._utc_naive(run.created_at_utc):
            return False
        return not (run.target == "rainfall_mm" and forecast.predicted_value < 0)

    @staticmethod
    def _utc_naive(value: datetime) -> datetime:
        return value if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
