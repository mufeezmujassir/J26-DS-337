"""Read-only final verification for the authorized Stage 12.3C.2 calendar run.

This command does not contact a source and does not write to PostgreSQL.  It
derives the completion decision from the persisted ingestion-run records and
holiday data, so a report cannot claim idempotency merely because a command was
invoked.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent
from app.holiday_event.source_access import load_terms_reviews


REPORTS = Path("data/reports")
POLICY = Path("config/holiday_event_source_policy.local.json")
ACCESS_REPORT = REPORTS / "stage12_3c_calendar_access_check.json"


def _json_file(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except json.JSONDecodeError:
        return None


def _write(name: str, value: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    reviews = load_terms_reviews(POLICY)
    policy = reviews.get("calendar_sri_lanka")
    access_report = _json_file(ACCESS_REPORT)

    async with AsyncSessionLocal() as db:
        total = int(await db.scalar(select(func.count()).select_from(Holiday)) or 0)
        poya = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(True))) or 0)
        public = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_public_holiday.is_(True))) or 0)
        bank = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_bank_holiday.is_(True))) or 0)
        missing_dates = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.event_date.is_(None))) or 0)
        missing_names = int(await db.scalar(select(func.count()).select_from(Holiday).where((Holiday.name.is_(None)) | (func.btrim(Holiday.name) == ""))) or 0)
        missing_sources = int(await db.scalar(select(func.count()).select_from(Holiday).where((Holiday.source_url.is_(None)) | (func.btrim(Holiday.source_url) == ""))) or 0)
        invalid_poya = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(True), Holiday.poya_name.is_(None))) or 0)
        duplicate_rows = (await db.execute(
            select(Holiday.event_date, Holiday.name, Holiday.source_url, func.count().label("count"))
            .group_by(Holiday.event_date, Holiday.name, Holiday.source_url)
            .having(func.count() > 1)
        )).all()
        runs = (await db.execute(
            select(IngestionRun)
            .join(IngestionSource, IngestionRun.source_id == IngestionSource.id)
            .where(IngestionSource.source_name == "Calendar Sri Lanka")
            .order_by(IngestionRun.id)
        )).scalars().all()
        revisions = int(await db.scalar(select(func.count()).select_from(HolidayEventRevision)) or 0)
        events = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)

    run_rows = [{
        "id": item.id,
        "status": item.status,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "records_fetched": item.records_fetched,
        "records_inserted": item.records_inserted,
        "records_updated": item.records_updated,
        "records_unchanged": item.records_unchanged,
        "records_rejected": item.records_rejected,
        "error_summary": item.error_summary,
    } for item in runs]
    completed = [row for row in run_rows if row["status"] == "SUCCEEDED"]
    recent = completed[-2:]
    repeat_ok = (
        len(recent) == 2
        and all(row["records_fetched"] == 1 for row in recent)
        and all(row["records_inserted"] == 0 for row in recent)
        and all(row["records_updated"] == 0 for row in recent)
        and all(row["records_unchanged"] == total for row in recent)
        and all(row["records_rejected"] == 0 for row in recent)
    )
    duplicates = [{"event_date": str(row.event_date), "name": row.name, "source_url": row.source_url, "count": row.count} for row in duplicate_rows]
    access = (access_report or {}).get("access", {})
    authorization = {
        "authorization_type": policy.authorization_type if policy else None,
        "authorization_status": policy.authorization_status if policy else None,
        "authorization_evidence": policy.authorization_evidence if policy else None,
        "authorization_scope": policy.authorization_scope if policy else None,
        "standing_authorization": policy.standing_authorization if policy else False,
        "terms_reviewed": policy.reviewed if policy else False,
        "terms_evidence_reference": policy.evidence_reference if policy else None,
        "robots_access_result": access,
        "limitation": "Authorization is user-attested verbal permission; it is not independent written website-terms evidence.",
    }
    quality = {
        "holiday_count": total,
        "poya_day_count": poya,
        "public_holiday_flag_count": public,
        "bank_holiday_flag_count": bank,
        "missing_dates": missing_dates,
        "missing_names": missing_names,
        "missing_source_urls": missing_sources,
        "invalid_poya_rows": invalid_poya,
        "duplicate_identity_groups": duplicates,
        "revision_count": revisions,
        "tourism_event_count": events,
        "classification_caveat": "The source table supplies a public/bank holiday page context. It does not explicitly distinguish those classifications for every individual row; existing values are preserved and must not be treated as finer-grained verified distinctions.",
    }
    idempotency = {
        "latest_two_successful_calendar_runs": recent,
        "repeat_verified": repeat_ok,
        "duplicates_created": len(duplicates),
        "revisions_created_by_repeat": 0 if repeat_ok else None,
        "interpretation": "Observation timestamps may change; source-content changes, duplicate inserts, and revisions must not occur when the source content is unchanged.",
    }
    clean_runs = not any(row["status"] == "RUNNING" for row in run_rows)
    verified = (
        access.get("permitted") is True
        and access.get("reason") == "AUTHORIZED_PUBLIC_CALENDAR_INGESTION"
        and total == 45
        and not duplicates
        and missing_dates == missing_names == missing_sources == invalid_poya == 0
        and repeat_ok
        and clean_runs
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "CALENDAR_INGESTION_VERIFIED" if verified else "CALENDAR_INGESTION_NOT_VERIFIED",
        "verification_basis": {
            "authorized_robots_check": access.get("reason"),
            "holiday_count": total,
            "two_repeat_runs_verified": repeat_ok,
            "duplicate_identity_groups": len(duplicates),
            "orphan_running_runs": [row["id"] for row in run_rows if row["status"] == "RUNNING"],
        },
        "postgresql_writes_executed_by_verifier": False,
        "qdrant_writes_executed": False,
    }
    _write("stage12_3c2_authorization_audit.json", authorization)
    _write("stage12_3c2_calendar_idempotency.json", idempotency)
    _write("stage12_3c2_data_quality.json", quality)
    _write("stage12_3c2_final_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
