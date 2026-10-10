"""Read-only API endpoints for persisted district-weather forecasts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.weather_forecast import WeatherForecast
from app.models.weather_model_run import WeatherModelRun


router = APIRouter(prefix="/api/v1/weather", tags=["Weather Intelligence"])
TARGETS = ("rainfall_mm", "temperature_max_c", "temperature_min_c")


async def _latest_runs(
    db: AsyncSession,
    district_id: int,
    *,
    include_unapproved: bool,
) -> list[WeatherModelRun]:
    statement = select(WeatherModelRun).where(WeatherModelRun.district_id == district_id)
    if not include_unapproved:
        statement = statement.where(WeatherModelRun.production_approved.is_(True))
    statement = statement.order_by(
        WeatherModelRun.created_at_utc.desc(), WeatherModelRun.run_id.desc()
    )
    candidates = list((await db.scalars(statement)).all())
    selected: dict[str, WeatherModelRun] = {}
    for run in candidates:
        if run.target in TARGETS and run.target not in selected:
            selected[run.target] = run
    return [selected[target] for target in TARGETS if target in selected]


async def _forecast_rows(
    db: AsyncSession, run_ids: list[str]
) -> dict[str, list[WeatherForecast]]:
    if not run_ids:
        return {}
    statement = (
        select(WeatherForecast)
        .where(WeatherForecast.run_id.in_(run_ids))
        .order_by(WeatherForecast.run_id, WeatherForecast.forecast_month)
    )
    rows = list((await db.scalars(statement)).all())
    grouped: dict[str, list[WeatherForecast]] = {run_id: [] for run_id in run_ids}
    for row in rows:
        grouped[row.run_id].append(row)
    return grouped


def _run_payload(run: WeatherModelRun, forecasts: list[WeatherForecast]) -> dict:
    return {
        "run_id": run.run_id,
        "target": run.target,
        "model": run.model_name,
        "training_start": run.training_start,
        "training_cutoff": run.training_cutoff,
        "latest_calendar_month": run.latest_calendar_month,
        "latest_observed_month": run.latest_observed_month,
        "latest_month_missing": run.latest_month_missing,
        "training_observations": run.training_observations,
        "validation_gate_passed": run.validation_gate_passed,
        "production_approved": run.production_approved,
        "status": run.status,
        "forecasts": [
            {
                "month": forecast.forecast_month,
                "predicted_value": forecast.predicted_value,
                "lower_bound": forecast.lower_bound,
                "upper_bound": forecast.upper_bound,
            }
            for forecast in forecasts
        ],
    }


@router.get("/forecasts/{district_id}")
async def get_district_forecasts(
    district_id: int,
    include_unapproved: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the latest persisted run per target; never train during a request."""
    runs = await _latest_runs(
        db, district_id, include_unapproved=include_unapproved
    )
    forecast_map = await _forecast_rows(db, [run.run_id for run in runs])
    models = [_run_payload(run, forecast_map[run.run_id]) for run in runs]
    message = None
    if not models:
        message = (
            "No production-approved forecasts are available for this district."
            if not include_unapproved
            else "No persisted weather forecasts are available for this district."
        )
    return {
        "district_id": district_id,
        "include_unapproved": include_unapproved,
        "models": models,
        "message": message,
    }


@router.get("/forecasts/{district_id}/status")
async def get_district_forecast_status(
    district_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return latest training freshness and validation state, including research runs."""
    runs = await _latest_runs(db, district_id, include_unapproved=True)
    if not runs:
        return {
            "district_id": district_id,
            "available": False,
            "message": "No persisted weather model runs are available for this district.",
            "models": [],
        }
    return {
        "district_id": district_id,
        "available": True,
        "models": [
            {
                "run_id": run.run_id,
                "target": run.target,
                "model": run.model_name,
                "training_observations": run.training_observations,
                "training_cutoff": run.training_cutoff,
                "latest_observed_month": run.latest_observed_month,
                "latest_month_missing": run.latest_month_missing,
                "validation_gate_passed": run.validation_gate_passed,
                "production_approved": run.production_approved,
                "status": run.status,
            }
            for run in runs
        ],
    }
