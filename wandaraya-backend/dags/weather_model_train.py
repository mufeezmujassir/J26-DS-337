"""Paused monthly candidate training; defaults to dry-run until explicitly enabled."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task

from app.weather_model.orchestration.airflow_tasks import train_weather_candidates


@dag(
    dag_id="weather_model_train", schedule=os.getenv("WEATHER_MODEL_TRAIN_SCHEDULE", "0 3 2 * *"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc), catchup=False,
    is_paused_upon_creation=True, max_active_runs=1, tags=["wandaraya", "weather", "training"],
)
def weather_model_train():
    @task(retries=1, retry_delay=timedelta(minutes=20), execution_timeout=timedelta(hours=3))
    def train_candidates():
        return train_weather_candidates()
    train_candidates()


weather_model_train()
