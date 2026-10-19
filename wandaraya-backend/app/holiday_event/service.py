"""Read-only holiday/event context and deterministic experimental scoring."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday_calendar import Holiday
from app.models.holiday_event import EventAttractionLink, TourismEvent


class HolidayEventContextService:
    policy_version = "holiday_event_experimental_v1"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def context(self, visit_datetime: datetime, attraction_id: int | None = None) -> dict:
        visit_date = visit_datetime.date()
        holidays = (await self.db.execute(select(Holiday).where(Holiday.event_date == visit_date))).scalars().all()
        event_query = select(TourismEvent).where(
            TourismEvent.status.in_(["scheduled", "unknown"]),
            or_(TourismEvent.start_datetime.is_(None), TourismEvent.start_datetime <= visit_datetime),
            or_(TourismEvent.end_datetime.is_(None), TourismEvent.end_datetime >= visit_datetime),
        )
        if attraction_id is not None:
            event_query = event_query.join(EventAttractionLink, EventAttractionLink.event_id == TourismEvent.id).where(
                EventAttractionLink.attraction_id == attraction_id,
                EventAttractionLink.verification_status == "verified",
            )
        events = (await self.db.execute(event_query)).scalars().all()
        holiday_items = [{"name": h.name, "type": h.event_type, "poya_name": h.poya_name, "confirmation_status": h.confirmation_status, "source_url": h.source_url} for h in holidays]
        event_items = [{"id": e.id, "title": e.title, "category": e.category, "status": e.status, "district_id": e.district_id, "source_url": e.source_url} for e in events]
        evidence = [x for x in [*(h.source_url for h in holidays), *(e.source_url for e in events)] if x]
        verified_event = attraction_id is not None and bool(events)
        score = 1.0 if verified_event else None
        return {
            "holiday_context": holiday_items,
            "active_events": event_items,
            "cultural_relevance": 1.0 if verified_event else None,
            "holiday_suitability_score": score,
            "evidence_confidence": "high" if verified_event else ("medium" if holiday_items or event_items else "unknown"),
            "source_provenance": evidence,
            "context_explanation": "Verified attraction-event relationship is active." if verified_event else ("Calendar/event records exist, but no attraction-specific suitability is inferred." if holiday_items or event_items else "No verified holiday or active event evidence is available."),
            "limitations": [] if verified_event else ["Holiday presence does not imply attraction closure, crowding, or suitability."],
            "scoring_policy_version": self.policy_version,
        }
