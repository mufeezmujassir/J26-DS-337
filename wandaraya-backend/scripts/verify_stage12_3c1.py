"""Read-only verification/reporting for Stage 12.3C.1 holiday ingestion."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent

OUTPUT = Path("data/reports")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        total = int(await db.scalar(select(func.count()).select_from(Holiday)) or 0)
        quality = {
            "total_holidays": total,
            "poya_days": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(True))) or 0),
            "public_holidays": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_public_holiday.is_(True))) or 0),
            "bank_holidays": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_bank_holiday.is_(True))) or 0),
            "missing_dates": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.event_date.is_(None))) or 0),
            "missing_names": int(await db.scalar(select(func.count()).select_from(Holiday).where((Holiday.name.is_(None)) | (func.btrim(Holiday.name) == ""))) or 0),
            "missing_source_urls": int(await db.scalar(select(func.count()).select_from(Holiday).where((Holiday.source_url.is_(None)) | (func.btrim(Holiday.source_url) == ""))) or 0),
            "invalid_poya_rows": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(True), Holiday.poya_name.is_(None))) or 0),
            "inconsistent_poya_rows": int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(False), Holiday.poya_name.is_not(None))) or 0),
            "earliest_date": str(await db.scalar(select(func.min(Holiday.event_date))) or ""),
            "latest_date": str(await db.scalar(select(func.max(Holiday.event_date))) or ""),
        }
        duplicate_groups = (await db.execute(
            select(Holiday.event_date, Holiday.name, Holiday.source_url, func.count().label("count"))
            .group_by(Holiday.event_date, Holiday.name, Holiday.source_url)
            .having(func.count() > 1)
        )).all()
        quality["duplicate_identity_groups"] = [
            {"event_date": str(row.event_date), "name": row.name, "source_url": row.source_url, "count": row.count}
            for row in duplicate_groups
        ]
        quality["classification_note"] = "Public/bank flags reflect explicit source-page classification context; record-level distinctions remain unknown where the source table does not state them individually."
        runs = (await db.execute(
            select(IngestionRun, IngestionSource.source_name)
            .join(IngestionSource, IngestionRun.source_id == IngestionSource.id)
            .where(IngestionSource.source_name == "Calendar Sri Lanka")
            .order_by(IngestionRun.id)
        )).all()
        run_rows = [{
            "id": run.id, "status": run.status, "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "records_fetched": run.records_fetched, "records_inserted": run.records_inserted,
            "records_updated": run.records_updated, "records_unchanged": run.records_unchanged,
            "records_rejected": run.records_rejected, "error_summary": run.error_summary,
        } for run, _source_name in runs]
        revision_count = int(await db.scalar(select(func.count()).select_from(HolidayEventRevision)) or 0)
        event_count = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
    serialization = {
        "status": "FIX_IMPLEMENTED",
        "strategy": "explicit typed JSON serializer for date, datetime, Decimal, UUID, Enum, nested dictionaries and lists",
        "observation_metadata_excluded_from_revisions": ["last_seen_at", "updated_at"],
        "regression_test_command": "python -m pytest tests/holiday_event/test_parsers.py -q",
    }
    idempotency = {
        "status": "PENDING_POST_FIX_REPEAT_INGESTION",
        "holiday_count_before_repeat": total,
        "revision_count_before_repeat": revision_count,
        "calendar_runs": run_rows,
        "requirement": "Run two successful post-fix permitted ingestions; the second must insert zero duplicates and create revisions only for genuine source-content changes.",
    }
    integrity = {"calendar_ingestion_runs": run_rows, "revision_count": revision_count, "orphan_running_runs": [row["id"] for row in run_rows if row["status"] == "RUNNING"]}
    final_status = "CALENDAR_INGESTION_VERIFIED" if len(run_rows) >= 3 and run_rows[-1]["status"] == "SUCCEEDED" and run_rows[-2]["status"] == "SUCCEEDED" and not duplicate_groups else "PENDING_POST_FIX_REPEAT_INGESTION"
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": final_status,
        "holiday_count": total,
        "tourism_event_count": event_count,
        "duplicate_identity_groups": len(duplicate_groups),
        "revision_count": revision_count,
        "postgresql_writes_executed_by_verifier": False,
        "qdrant_writes_executed": False,
    }
    payloads = {
        "stage12_3c1_serialization_fix.json": serialization,
        "stage12_3c1_holiday_data_quality.json": quality,
        "stage12_3c1_idempotency.json": idempotency,
        "stage12_3c1_ingestion_run_integrity.json": integrity,
        "stage12_3c1_final_summary.json": summary,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (OUTPUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
