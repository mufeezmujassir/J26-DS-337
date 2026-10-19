"""Read-only implementation/access report for Stage 12.3C.3 LankaEvents."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.holiday_event import HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent
from app.holiday_event.source_access import load_terms_reviews

REPORTS = Path("data/reports")


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except json.JSONDecodeError:
        return None


def save(name: str, payload: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    policy = load_terms_reviews("config/holiday_event_source_policy.local.json").get("lanka_events")
    access_run = read_json(REPORTS / "stage12_3c3_lankaevents_access_runtime.json") or {}
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(IngestionSource).where(IngestionSource.source_name == "LankaEvents"))).scalar_one_or_none()
        event_count = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
        revisions = int(await db.scalar(select(func.count()).select_from(HolidayEventRevision).where(HolidayEventRevision.record_type == "event")) or 0)
        runs = [] if source is None else (await db.execute(select(IngestionRun).where(IngestionRun.source_id == source.id).order_by(IngestionRun.id))).scalars().all()
    run_rows = [{"id": r.id, "status": r.status, "records_fetched": r.records_fetched, "records_inserted": r.records_inserted, "records_updated": r.records_updated, "records_unchanged": r.records_unchanged, "records_rejected": r.records_rejected, "error_summary": r.error_summary} for r in runs]
    permitted = bool((access_run.get("access") or {}).get("permitted"))
    report_access = {
        "policy_configured": {
            "terms_reviewed": policy.reviewed if policy else False,
            "automated_collection_permitted": policy.automated_collection_permitted if policy else False,
            "terms_evidence_reference": policy.evidence_reference if policy else None,
            "allowed_detail_path_prefixes": list(policy.allowed_detail_path_prefixes) if policy else [],
        },
        "latest_access_check": access_run.get("access"),
        "live_collection_permitted": permitted,
        "decision": "No live event discovery was run because terms evidence/detail URL permissions are incomplete." if not permitted else "Access check permits controlled collection.",
    }
    discovery = {"months_requested": ["current", "next_1", "next_2", "next_3"], "months_successfully_processed": [], "events_discovered": 0, "unique_event_identities": 0, "detail_pages_attempted": 0, "detail_pages_successful": 0, "detail_pages_failed": 0, "events_excluded_by_limit": 0, "configured_detail_cap": 50, "status": "PENDING_PERMITTED_LIVE_DISCOVERY"}
    extraction = {"events_extracted": 0, "status": "PARSER_IMPLEMENTED_FIXTURE_VERIFIED", "live_extraction_claimed": False}
    quality = {"events_scored": 0, "status": "PENDING_LIVE_RECORDS", "quality_dimensions": ["title", "start_date", "date_range", "source_url", "category", "venue", "location_confidence", "organizer", "description"]}
    db_report = {"tourism_events": event_count, "event_revisions": revisions, "ingestion_runs": run_rows, "postgresql_writes_executed_by_report": False, "qdrant_writes_executed": False}
    idempotency = {"status": "PENDING_PERMITTED_LIVE_REPEAT", "duplicate_event_identities": 0, "revision_count": revisions}
    airflow = {"dag_id": "sri_lanka_events_daily_ingestion", "schedule": "30 0 * * *", "timezone": "Asia/Colombo", "status": "IMPLEMENTED_PAUSED_PENDING_LIVE_VERIFICATION"}
    api = {"routes": ["GET /api/v1/events", "GET /api/v1/events/upcoming", "GET /api/v1/events/{event_id}", "GET /api/v1/context/holiday-events"], "event_records_available": event_count, "status": "NO_LIVE_EVENT_READBACK_AVAILABLE"}
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": "LANKAEVENTS_INGESTION_VERIFIED" if permitted and event_count else "LANKAEVENTS_IMPLEMENTED_PENDING_SOURCE_ACCESS", "blockers": [] if permitted else ["documented LankaEvents terms evidence", "explicit permitted public detail URL path prefixes", "controlled live extraction and repeat idempotency verification"], "tourism_events": event_count, "postgresql_writes_executed_by_report": False, "qdrant_writes_executed": False}
    for name, payload in {
        "stage12_3c3_lankaevents_access.json": report_access,
        "stage12_3c3_event_discovery.json": discovery,
        "stage12_3c3_event_extraction.json": extraction,
        "stage12_3c3_event_quality.json": quality,
        "stage12_3c3_database_ingestion.json": db_report,
        "stage12_3c3_idempotency.json": idempotency,
        "stage12_3c3_airflow_validation.json": airflow,
        "stage12_3c3_api_readback.json": api,
        "stage12_3c3_final_summary.json": summary,
    }.items():
        save(name, payload)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
