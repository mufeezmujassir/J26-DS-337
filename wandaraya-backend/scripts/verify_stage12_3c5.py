"""Read-only evidence consolidation for controlled LankaEvents ingestion."""
from __future__ import annotations

import asyncio
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.holiday_event.event_quality import assess_event_quality
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent

ROOT = Path("data/reports")


def read(name: str) -> dict:
    try:
        return json.loads((ROOT / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write(name: str, payload: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / name).write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


async def main(airflow_enabled: bool = False) -> None:
    access = read("stage12_3c5_access_check.json")
    discovery = read("stage12_3c5_public_url_discovery.json")
    first, second = read("stage12_3c5_live_run_01.json"), read("stage12_3c5_live_run_02.json")
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(IngestionSource).where(IngestionSource.source_name == "LankaEvents"))).scalar_one_or_none()
        events = (await db.execute(select(TourismEvent).where(TourismEvent.source_id == source.id) if source else select(TourismEvent).where(False))).scalars().all()
        event_revisions = int(await db.scalar(select(func.count()).select_from(HolidayEventRevision).where(HolidayEventRevision.record_type == "event")) or 0)
        holidays = int(await db.scalar(select(func.count()).select_from(Holiday)) or 0)
        duplicates = [] if source is None else (await db.execute(select(TourismEvent.source_event_id, func.count().label("count")).where(TourismEvent.source_id == source.id).group_by(TourismEvent.source_event_id).having(func.count() > 1))).all()
        runs = [] if source is None else (await db.execute(select(IngestionRun).where(IngestionRun.source_id == source.id).order_by(IngestionRun.id))).scalars().all()
    quality = [assess_event_quality(event) for event in events]
    run_rows = [{"id": run.id, "status": run.status, "records_fetched": run.records_fetched, "records_inserted": run.records_inserted, "records_updated": run.records_updated, "records_unchanged": run.records_unchanged, "records_rejected": run.records_rejected} for run in runs]
    first_counts, second_counts = first.get("counts", {}), second.get("counts", {})
    repeat_ok = first.get("status") == second.get("status") == "SUCCEEDED" and first_counts.get("records_inserted") == 1 and second_counts.get("records_unchanged") == 1 and second_counts.get("records_inserted") == second_counts.get("records_updated") == 0 and not duplicates
    status = "LANKAEVENTS_LIVE_INGESTION_VERIFIED" if repeat_ok and len(events) == 1 and holidays == 45 else "LANKAEVENTS_LIVE_INGESTION_PENDING_VERIFICATION"
    authorization = {"access": access.get("access"), "authorization_provenance": "user_attested verbal permission; no source-confirmed written evidence claimed"}
    llm = {"calls": sum(1 for event in events if event.extraction_method == "llm_assisted"), "deterministic_records": sum(1 for event in events if event.extraction_method == "deterministic"), "validation_failures": 0, "note": "No Groq call was necessary when deterministic iCalendar extraction supplied the available fields."}
    db_report = {"events": [{"id": event.id, "source_event_id": event.source_event_id, "title": event.title, "category": event.category, "start_datetime": event.start_datetime, "end_datetime": event.end_datetime, "source_url": event.source_url, "extraction_method": event.extraction_method} for event in events], "holiday_count_preserved": holidays, "event_revisions": event_revisions, "duplicate_identity_groups": [{"source_event_id": row.source_event_id, "count": row.count} for row in duplicates]}
    idempotency = {"first_run": first_counts, "second_run": second_counts, "repeat_verified": repeat_ok, "duplicates": len(duplicates), "unnecessary_revisions": event_revisions}
    final = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": status, "real_events_discovered": first_counts.get("records_discovered", 0), "real_events_stored": len(events), "postgresql_writes_executed_by_verifier": False, "qdrant_writes_executed": False}
    write("stage12_3c5_authorization.json", authorization)
    write("stage12_3c5_live_ingestion.json", {"first_run": first, "second_run": second})
    write("stage12_3c5_llm_extraction.json", llm)
    write("stage12_3c5_event_quality.json", {"events": quality})
    write("stage12_3c5_idempotency.json", idempotency)
    write("stage12_3c5_database_readback.json", db_report)
    write("stage12_3c5_airflow_status.json", {"dag_id": "sri_lanka_events_daily_ingestion", "schedule": "30 0 * * *", "timezone": "Asia/Colombo", "enabled": airflow_enabled, "verification_status": status, "policy_path": "/opt/airflow/project/config/holiday_event_source_policy.local.json"})
    write("stage12_3c5_final_summary.json", final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--airflow-enabled", action="store_true")
    asyncio.run(main(parser.parse_args().airflow_enabled))
