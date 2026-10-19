"""Paused daily LankaEvents ingestion with source governance and bounded scope."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

LOCAL = ZoneInfo("Asia/Colombo")


@dag(
    dag_id="sri_lanka_events_daily_ingestion",
    schedule="30 0 * * *",
    start_date=datetime(2026, 1, 1, tzinfo=LOCAL),
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=["events", "sri-lanka", "source-governed"],
)
def events_dag():
    @task(retries=2, retry_delay=timedelta(minutes=10), execution_timeout=timedelta(minutes=15))
    def ingest() -> dict:
        if os.getenv("HOLIDAY_EVENT_SCHEDULED_INGESTION_ENABLED") != "true":
            return {"status": "SCHEDULED_INGESTION_DISABLED", "writes": 0}
        from app.database import AsyncSessionLocal
        from app.holiday_event.ingestion import HolidayEventIngestionService
        from app.holiday_event.repository import HolidayEventRepository
        from app.holiday_event.source_access import load_terms_reviews

        policy_path = os.getenv("HOLIDAY_EVENT_SOURCE_POLICY_PATH")
        reviews = load_terms_reviews(policy_path)

        async def run() -> dict:
            async with AsyncSessionLocal() as session:
                return await HolidayEventIngestionService(HolidayEventRepository(session)).run(
                    "lanka_events", dag_id="sri_lanka_events_daily_ingestion",
                    terms_review=reviews.get("lanka_events"), execute=True,
                    event_horizon_months=3, max_event_details=50,
                )
        return asyncio.run(run())

    ingest()


events_dag()
