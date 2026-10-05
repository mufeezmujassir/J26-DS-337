"""Monthly nationwide attraction discovery, kept separate from KB refresh."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from airflow.decorators import dag, task


logger = logging.getLogger(__name__)
API_URL = os.getenv("WANDARAYA_API_URL", "http://fastapi:8000").rstrip("/")
API_TOKEN = os.getenv("AIRFLOW_API_TOKEN", "")


def run_discovery() -> dict:
    if len(API_TOKEN) < 32:
        raise RuntimeError("AIRFLOW_API_TOKEN must be a random secret of at least 32 characters.")
    request = Request(
        f"{API_URL}/internal/knowledge-base/discovery",
        data=json.dumps({"ingest": True}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Airflow-Token": API_TOKEN,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=3600) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Discovery API returned HTTP {error.code}: {detail[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the discovery API: {error.reason}") from error


@dag(
    dag_id="wandaraya_tourism_attraction_discovery",
    schedule="@monthly",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["wandaraya", "tourism", "knowledge-base", "discovery"],
)
def tourism_attraction_discovery():
    @task(retries=2, retry_delay=timedelta(minutes=2))
    def discover_attractions() -> dict:
        result = run_discovery()
        logger.info(
            "Discovery result | discovered=%s known=%s new=%s ingested=%s failed=%s",
            result["discovered"],
            result["already_known"],
            result["new"],
            result["ingested_successfully"],
            result["ingested_failed"],
        )
        return result

    discover_attractions()


tourism_attraction_discovery()
