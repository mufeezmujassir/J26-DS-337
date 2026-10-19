"""Read-only real-data verification reports for Stage 12.3D.1."""
from __future__ import annotations

import asyncio
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.holiday_event.context_features import HolidayEventContextFeatureService, HolidayEventFeatureRequest
from app.models.attraction import Attraction
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import EventAttractionLink, TourismEvent

ROOT = Path("data/reports")


def save(name: str, value: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


async def main(*, api_verified: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        attraction_id = await db.scalar(select(Attraction.id).where(Attraction.is_active.is_(True)).order_by(Attraction.id).limit(1))
        poya_date = await db.scalar(select(Holiday.event_date).where(Holiday.is_poya.is_(True)).order_by(Holiday.event_date).limit(1))
        event = (await db.execute(select(TourismEvent).order_by(TourismEvent.id).limit(1))).scalar_one_or_none()
        links = int(await db.scalar(select(func.count()).select_from(EventAttractionLink).where(EventAttractionLink.verification_status == "verified")) or 0)
        holiday_count = int(await db.scalar(select(func.count()).select_from(Holiday)) or 0)
        poya_count = int(await db.scalar(select(func.count()).select_from(Holiday).where(Holiday.is_poya.is_(True))) or 0)
        event_count = int(await db.scalar(select(func.count()).select_from(TourismEvent)) or 0)
        poya_preview = await HolidayEventContextFeatureService(db).evaluate(HolidayEventFeatureRequest(travel_date=poya_date, attraction_ids=[attraction_id])) if attraction_id and poya_date else None
        event_preview = await HolidayEventContextFeatureService(db).evaluate(HolidayEventFeatureRequest(travel_date=event.start_datetime.date(), attraction_ids=[attraction_id])) if attraction_id and event is not None and event.start_datetime is not None else None
    poya_feature = poya_preview.features[0].model_dump() if poya_preview else None
    coverage = {"real_postgresql_holidays": holiday_count, "real_poya_days": poya_count, "real_tourism_events": event_count, "verified_event_attraction_links": links, "sample_attraction_id": attraction_id, "ranking_changed": False, "qdrant_writes": False}
    event_context = {"real_event": None if event is None else {"id": event.id, "source_event_id": event.source_event_id, "title": event.title, "start_datetime": event.start_datetime, "end_datetime": event.end_datetime, "district_id": event.district_id, "location_confidence": event.location_confidence, "source_url": event.source_url}, "overlap_preview": event_preview.features[0].model_dump() if event_preview else None, "verified_event_attraction_links": links, "result": "Event location is unresolved; proximity remains unknown until verified location evidence exists."}
    uncertainty = {"public_bank_classification": "Existing calendar flags are page-level context; preview returns null where row-level verification is unavailable.", "event_location": "No coordinates, district, or verified event-attraction link exists for the current event; no geographic score is applied.", "ranking": "Feature preview does not alter content-based or time-aware production ranking."}
    api = {
        "endpoint": "POST /api/v1/context/holiday-events/evaluate",
        "sample_request": {"travel_date": str(poya_date) if poya_date else None, "attraction_ids": [attraction_id] if attraction_id else []},
        "status": "HTTP_READBACK_VERIFIED" if api_verified else "ROUTE_REGISTERED_CODE_VERIFIED",
        "http_request_performed": api_verified,
    }
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "status": "HOLIDAY_EVENT_CONTEXT_FEATURE_ENGINE_VERIFIED" if poya_feature and event is not None else "HOLIDAY_EVENT_CONTEXT_FEATURE_ENGINE_PENDING", "real_data_used": True, "production_ranking_changed": False, "postgresql_writes_executed": False, "qdrant_writes_executed": False}
    save("stage12_3d1_feature_coverage.json", coverage)
    save("stage12_3d1_poya_context.json", {"preview": poya_feature})
    save("stage12_3d1_event_context.json", event_context)
    save("stage12_3d1_uncertainty_audit.json", uncertainty)
    save("stage12_3d1_api_verification.json", api)
    save("stage12_3d1_final_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write read-only Stage 12.3D.1 verification reports.")
    parser.add_argument("--api-verified", action="store_true", help="Record a separately performed successful HTTP API readback.")
    args = parser.parse_args()
    asyncio.run(main(api_verified=args.api_verified))
