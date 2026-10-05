from __future__ import annotations
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task

logger = logging.getLogger(__name__)

API_URL = os.getenv(
    "WANDARAYA_API_URL",
    "http://fastapi:8000",
).rstrip("/")

API_TOKEN = os.getenv("AIRFLOW_API_TOKEN", "")


def run_refresh() -> dict:
    if len(API_TOKEN) < 32:
        raise RuntimeError(
            "AIRFLOW_API_TOKEN must be set to a random secret of at least 32 characters."
        )

    request = Request(
        f"{API_URL}/internal/knowledge-base/refresh",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Airflow-Token": API_TOKEN,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=1800) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Knowledge-base refresh API returned HTTP {error.code}: {detail[:500]}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Could not reach the knowledge-base refresh API: {error.reason}"
        ) from error


@dag(
    dag_id="wandaraya_tourism_kb_refresh",

    # Monthly for now.
    schedule="@monthly",

    start_date=datetime(
        2026,
        10,
        1,
        tzinfo=timezone.utc,
    ),

    catchup=False,

    max_active_runs=1,

    tags=[
        "wandaraya",
        "tourism",
        "knowledge-base",
        "mlops",
    ],
)
def tourism_kb_refresh():

    # ========================================================
    # TASK 1
    # START
    # ========================================================

    @task
    def start_refresh() -> dict:

        started_at = datetime.now(
            timezone.utc
        )

        logger.info(
            "Starting WANDARAYA Tourism KB refresh."
        )

        return {
            "started_at": started_at.isoformat()
        }

    # ========================================================
    # TASK 2
    # REFRESH
    # ========================================================

    @task(
        retries=2,
        retry_delay=timedelta(
            minutes=1
        )
    )
    def refresh_attractions(
        start_info: dict,
    ) -> dict:

        logger.info(
            "Refresh started at %s",
            start_info["started_at"],
        )

        result = run_refresh()

        logger.info(
            (
                "KB refresh result | "
                "requested=%s "
                "successful=%s "
                "skipped=%s "
                "failed=%s"
            ),
            result["requested"],
            result["successful"],
            result["skipped"],
            result["failed"],
        )

        return result

    # ========================================================
    # TASK 3
    # VALIDATE RESULT
    # ========================================================

    @task
    def validate_refresh(
        result: dict,
    ) -> dict:

        requested = int(
            result["requested"]
        )

        successful = int(
            result["successful"]
        )

        skipped = int(
            result["skipped"]
        )

        failed = int(
            result["failed"]
        )

        processed = (
            successful
            + skipped
            + failed
        )

        if processed != requested:

            raise RuntimeError(
                (
                    "Refresh accounting mismatch | "
                    f"requested={requested} "
                    f"processed={processed}"
                )
            )

        if failed > 0:

            logger.warning(
                "KB refresh completed with %s failures.",
                failed,
            )

            for error in result.get(
                "errors",
                [],
            ):
                logger.warning(
                    "Refresh error: %s",
                    error,
                )

        return result



    @task
    def refresh_summary(
        result: dict,
    ) -> None:

        logger.info(
            "========================================"
        )

        logger.info(
            "WANDARAYA TOURISM KB REFRESH SUMMARY"
        )

        logger.info(
            "========================================"
        )

        logger.info(
            "Requested:  %s",
            result["requested"],
        )

        logger.info(
            "Successful: %s",
            result["successful"],
        )

        logger.info(
            "Skipped:    %s",
            result["skipped"],
        )

        logger.info(
            "Failed:     %s",
            result["failed"],
        )

        logger.info(
            "Refreshed IDs: %s",
            result["refreshed_attraction_ids"],
        )

        logger.info(
            "Started:  %s",
            result["started_at"],
        )

        logger.info(
            "Finished: %s",
            result["finished_at"],
        )

        logger.info(
            "========================================"
        )

    # ========================================================
    # DEPENDENCY FLOW
    # ========================================================

    start = start_refresh()

    refresh_result = refresh_attractions(
        start
    )

    validated_result = validate_refresh(
        refresh_result
    )

    refresh_summary(
        validated_result
    )


tourism_kb_refresh()