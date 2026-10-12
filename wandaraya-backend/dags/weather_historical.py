"""Paused monthly verified-historical import; no import command is assumed."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task

from app.weather_model.orchestration.airflow_tasks import import_verified_historical_weather


@dag(
    dag_id="weather_historical", schedule=os.getenv("WEATHER_HISTORICAL_SCHEDULE", "0 2 1 * *"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc), catchup=False,
    is_paused_upon_creation=True, max_active_runs=1, tags=["wandaraya", "weather", "historical"],
)
def weather_historical():
    @task(retries=1, retry_delay=timedelta(minutes=15), execution_timeout=timedelta(hours=2))
    def import_verified():
        return import_verified_historical_weather()
    import_verified()


weather_historical()
