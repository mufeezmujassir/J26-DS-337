"""Create factual Stage 12.3C status reports without network or database writes."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import IngestionRun, TourismEvent

OUTPUT = Path("data/reports")


def _load_report(name: str) -> dict | None:
    path = OUTPUT / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


async def main() -> None:
    stage12_3c2_summary = _load_report("stage12_3c2_final_summary.json")
    async with AsyncSessionLocal() as db:
        holidays = int(await db.scalar(select(func.count()).select_from(Holiday)) or 0)
        events = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
        runs = (await db.execute(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(20))).scalars().all()
    run_rows = [{
        "id": run.id, "source_id": run.source_id, "dag_id": run.dag_id, "status": run.status,
        "records_fetched": run.records_fetched, "records_inserted": run.records_inserted,
        "records_updated": run.records_updated, "records_unchanged": run.records_unchanged,
        "records_rejected": run.records_rejected, "error_summary": run.error_summary,
    } for run in runs]
    access = {
        "status": "TERMS_REVIEW_REQUIRED_FOR_LIVE_INGESTION",
        "calendar_sri_lanka": "robots rules must be rechecked at each execution; terms evidence not supplied to this report",
        "lanka_events": "NO_ROBOTS_RULES_FOUND is not a prohibition; terms evidence is still required before automation",
    }
    calendar = {"status": "NO_LIVE_EXTRACTION_CLAIMED", "holiday_records_in_database": holidays}
    events_report = {"status": "NO_LIVE_EXTRACTION_CLAIMED", "event_records_in_database": events, "maximum_discovery_horizon_months": 3}
    database = {"holiday_calendar": holidays, "tourism_events": events, "recent_ingestion_runs": run_rows, "postgresql_writes_executed_by_report": False, "qdrant_writes_executed": False}
    verified = stage12_3c2_summary and stage12_3c2_summary.get("status") == "CALENDAR_INGESTION_VERIFIED"
    idempotency = {"status": "VERIFIED_BY_STAGE12_3C2" if verified else "PENDING_LIVE_REPEAT_VERIFICATION", "reason": None if verified else "no successful source ingestion run has been verified by this reporting command"}
    airflow = {
        "annual_calendar_dag": "ENABLED_AFTER_C2_VERIFICATION" if verified else "IMPLEMENTED_PAUSED",
        "daily_events_dag": "IMPLEMENTED_PAUSED",
        "scheduled_enablement_requires": ["HOLIDAY_EVENT_SCHEDULED_INGESTION_ENABLED=true", "reviewed local source policy"],
        "runtime_policy_path": "/opt/airflow/project/config/holiday_event_source_policy.local.json" if verified else None,
    }
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": "CALENDAR_INGESTION_VERIFIED" if verified else "IMPLEMENTED_PENDING_PERMITTED_LIVE_INGESTION", "completion_blockers": [] if verified else ["documented source terms evidence", "controlled live extraction", "repeat idempotency verification", "Airflow registration/runtime verification"], "database": database, "qdrant_writes_executed": False, "stage12_3c2_verification": stage12_3c2_summary}
    calendar_access = _load_report("stage12_3c_calendar_access_check.json")
    calendar_live = {
        "status": "NOT_EXECUTED" if calendar_access is None else "BLOCKED_BEFORE_LIVE_INGESTION",
        "access_result": calendar_access.get("access") if calendar_access else None,
        "reason": "No live calendar extraction or PostgreSQL holiday write is claimed until documented terms evidence is present.",
        "postgresql_domain_records_written": False,
        "qdrant_writes": False,
    }
    calendar_idempotency = {
        "status": "PENDING_FIRST_PERMITTED_INGESTION",
        "first_run": None,
        "second_run": None,
        "duplicates_created": 0,
        "reason": "A repeat run cannot be evaluated before a successful permitted first run.",
    }
    readback = {
        "holiday_calendar_records": holidays,
        "tourism_event_records": events,
        "readback_status": "NO_LIVE_INGESTION_TO_VERIFY" if holidays == 0 and events == 0 else "REVIEW_LATEST_INGESTION_RUN",
        "postgresql_writes_executed_by_report": False,
        "qdrant_writes_executed": False,
    }
    outputs = {
        "stage12_3c_source_access_audit.json": access,
        "stage12_3c_calendar_extraction.json": calendar,
        "stage12_3c_event_extraction.json": events_report,
        "stage12_3c_database_ingestion.json": database,
        "stage12_3c_idempotency.json": idempotency,
        "stage12_3c_airflow_validation.json": airflow,
        "stage12_3c_final_summary.json": summary,
        "stage12_3c_calendar_live_ingestion.json": calendar_live,
        "stage12_3c_calendar_idempotency.json": calendar_idempotency,
        "stage12_3c_database_readback.json": readback,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        (OUTPUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
