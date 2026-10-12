"""Paused weekly cache refresh using only live or approved-model forecasts."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task

from app.weather_model.orchestration.airflow_tasks import refresh_prediction_cache


@dag(
    dag_id="weather_predictions_cache", schedule=os.getenv("WEATHER_PREDICTIONS_CACHE_SCHEDULE", "0 4 * * 1"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc), catchup=False,
    is_paused_upon_creation=True, max_active_runs=1, tags=["wandaraya", "weather", "forecast-cache"],
)
def weather_predictions_cache():
    @task(retries=2, retry_delay=timedelta(minutes=10), execution_timeout=timedelta(minutes=30))
    def refresh(logical_date=None):
        return refresh_prediction_cache((logical_date or datetime.now(timezone.utc)).date())
    refresh()


weather_predictions_cache()
