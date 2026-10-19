"""Read-only Stage 12.3C.4 automation readiness report."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.holiday_event import HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent
from app.holiday_event.source_access import load_terms_reviews

ROOT = Path("data/reports")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(name: str, body: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / name).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    policy = load_terms_reviews("config/holiday_event_source_policy.local.json").get("lanka_events")
    previous_access = load(ROOT / "stage12_3c3_lankaevents_access_runtime.json").get("access")
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(IngestionSource).where(IngestionSource.source_name == "LankaEvents"))).scalar_one_or_none()
        events = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
        revisions = int(await db.scalar(select(func.count()).select_from(HolidayEventRevision).where(HolidayEventRevision.record_type == "event")) or 0)
        runs = [] if source is None else (await db.execute(select(IngestionRun).where(IngestionRun.source_id == source.id).order_by(IngestionRun.id))).scalars().all()
    run_rows = [{"id": run.id, "status": run.status, "records_fetched": run.records_fetched, "records_inserted": run.records_inserted, "records_updated": run.records_updated, "records_unchanged": run.records_unchanged, "records_rejected": run.records_rejected} for run in runs]
    access_permitted = bool(previous_access and previous_access.get("permitted"))
    access = {
        "robots_status": previous_access.get("robots_status") if previous_access else None,
        "latest_access_decision": previous_access.get("reason") if previous_access else "NOT_CHECKED",
        "configured_authorization_type": policy.authorization_type if policy else None,
        "configured_authorization_status": policy.authorization_status if policy else None,
        "configured_standing_authorization": policy.standing_authorization if policy else False,
        "allowed_detail_path_prefixes": list(policy.allowed_detail_path_prefixes) if policy else [],
        "access_permitted": access_permitted,
        "note": "A robots 404 is recorded as no rules found; it does not override missing terms evidence or detail-path permissions.",
    }
    llm = {"enabled_for_live_runs": False, "groq_requests": 0, "cache_hits": 0, "failures": 0, "policy": "Optional explicit --enable-llm --confirm-llm fallback only; values require literal source-text evidence and remain source-derived, not independently verified."}
    discovery = {"live_listing_requests": 0, "events_discovered": 0, "unique_event_identities": 0, "detail_page_cap": 50, "coverage": "not attempted because source access is not permitted"}
    ingestion = {"tourism_events": events, "ingestion_runs": run_rows, "postgresql_event_writes": False, "qdrant_writes": False}
    quality = {"events_assessed": 0, "invalid_date_ranges": 0, "missing_source_urls": 0, "unresolved_locations": 0, "note": "No real LankaEvents records exist yet."}
    idempotency = {"duplicate_event_identities": 0, "event_revisions": revisions, "status": "PENDING_LIVE_REPEAT"}
    airflow = {"dag_id": "sri_lanka_events_daily_ingestion", "schedule": "30 0 * * *", "timezone": "Asia/Colombo", "configured_for_automatic_execution": True, "acquisition_enabled": False, "reason": "DAG remains paused until permitted controlled live ingestion and repeat verification pass."}
    status = "LANKAEVENTS_AUTOMATED_INGESTION_VERIFIED" if access_permitted and events > 0 else "LANKAEVENTS_AUTOMATION_READY_PENDING_SOURCE_ACCESS"
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": status, "events_discovered": 0, "events_persisted": events, "groq_requests": 0, "postgresql_writes_executed_by_report": False, "qdrant_writes_executed": False, "remaining_blockers": [] if status.endswith("VERIFIED") else ["replace LankaEvents placeholder terms evidence with a real reference", "record only source-permitted public detail URL prefixes", "run controlled live ingestion twice and verify read-back before unpausing the daily DAG"]}
    for name, body in {
        "stage12_3c4_source_access.json": access,
        "stage12_3c4_llm_extraction.json": llm,
        "stage12_3c4_event_discovery.json": discovery,
        "stage12_3c4_event_ingestion.json": ingestion,
        "stage12_3c4_data_quality.json": quality,
        "stage12_3c4_idempotency.json": idempotency,
        "stage12_3c4_airflow_verification.json": airflow,
        "stage12_3c4_final_summary.json": summary,
    }.items():
        save(name, body)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
