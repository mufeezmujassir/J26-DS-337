"""Paused annual Calendar Sri Lanka ingestion with a fail-closed access gate."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

LOCAL = ZoneInfo("Asia/Colombo")


@dag(
    dag_id="sri_lanka_annual_calendar_ingestion",
    schedule="15 0 1 1 *",
    start_date=datetime(2026, 1, 1, tzinfo=LOCAL),
    catchup=False,
    is_paused_upon_creation=True,
    max_active_runs=1,
    tags=["holiday", "sri-lanka", "source-governed"],
)
def calendar_dag():
    @task(retries=2, retry_delay=timedelta(minutes=10), execution_timeout=timedelta(minutes=15))
    def ingest() -> dict:
        # A scheduler cannot silently enable a source: deployment must mount the
        # reviewed local policy and explicitly set this flag after review.
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
                    "calendar_sri_lanka", dag_id="sri_lanka_annual_calendar_ingestion",
                    terms_review=reviews.get("calendar_sri_lanka"), execute=True,
                )
        return asyncio.run(run())

    ingest()


calendar_dag()
