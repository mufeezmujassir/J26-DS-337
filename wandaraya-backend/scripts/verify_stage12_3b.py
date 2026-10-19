"""Read-only Stage 12.3B production verification and report generation."""
import asyncio, json
from pathlib import Path
from sqlalchemy import func, select, text
from app.database import AsyncSessionLocal
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import EventAttractionLink, HolidayEventRevision, IngestionRun, IngestionSource, TourismEvent

ROOT=Path("data/reports")
async def main():
    async with AsyncSessionLocal() as db:
        names=(await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all()
        counts={"holiday_calendar":await db.scalar(select(func.count()).select_from(Holiday)),"ingestion_sources":await db.scalar(select(func.count()).select_from(IngestionSource)),"ingestion_runs":await db.scalar(select(func.count()).select_from(IngestionRun)),"tourism_events":await db.scalar(select(func.count()).select_from(TourismEvent)),"event_attraction_links":await db.scalar(select(func.count()).select_from(EventAttractionLink)),"holiday_event_revisions":await db.scalar(select(func.count()).select_from(HolidayEventRevision))}
    schema={"status":"SCHEMA_VERIFIED" if all(key in names for key in counts) else "SCHEMA_MISMATCH","tables":counts,"postgresql_writes":False,"qdrant_writes":False}
    for name, body in {"stage12_3b_schema_verification.json":schema,"stage12_3b_source_registration.json":{"status":"READ_ONLY","source_count":counts["ingestion_sources"]},"stage12_3b_holiday_persistence.json":{"status":"NO_LIVE_INGESTION_EXECUTED","count":counts["holiday_calendar"]},"stage12_3b_event_persistence.json":{"status":"NO_LIVE_INGESTION_EXECUTED","count":counts["tourism_events"]},"stage12_3b_idempotency_results.json":{"status":"IMPLEMENTED_NOT_LIVE_VERIFIED"},"stage12_3b_api_integration.json":{"status":"ROUTER_REGISTERED_RESTART_REQUIRED_FOR_LIVE_HTTP"},"stage12_3b_test_results.json":{"status":"LOCAL_TESTS_EXECUTED"},"stage12_3b_final_summary.json":{"status":"PERSISTENCE_IMPLEMENTED_PENDING_LIVE_VERIFICATION","counts":counts,"postgresql_writes":False,"qdrant_writes":False}}.items(): (ROOT/name).write_text(json.dumps(body,indent=2)+"\n")
    print(json.dumps(schema,indent=2))
asyncio.run(main())
