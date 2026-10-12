"""Paused three-hourly live weather cache refresh."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task

from app.weather_model.orchestration.airflow_tasks import refresh_live_weather_cache


@dag(
    dag_id="weather_live", schedule=os.getenv("WEATHER_LIVE_SCHEDULE", "0 */3 * * *"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc), catchup=False,
    is_paused_upon_creation=True, max_active_runs=1, tags=["wandaraya", "weather", "live"],
)
def weather_live():
    @task(retries=2, retry_delay=timedelta(minutes=5), execution_timeout=timedelta(minutes=10))
    def refresh(logical_date=None):
        return refresh_live_weather_cache((logical_date or datetime.now(timezone.utc)).date())
    refresh()


weather_live()
