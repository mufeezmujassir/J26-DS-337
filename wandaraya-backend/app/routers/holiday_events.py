"""Evidence-backed calendar, event, and experimental holiday-context APIs."""
from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.holiday_event.service import HolidayEventContextService
from app.models.holiday_calendar import Holiday
from app.models.holiday_event import TourismEvent

router = APIRouter(tags=["Holiday and Event Intelligence"])

def _limit(limit: int) -> int:
    return min(max(limit, 1), 100)

@router.get("/api/v1/calendar/holidays")
async def holidays(date_value: date | None = Query(None, alias="date"), start_date: date | None = None, end_date: date | None = None, holiday_type: str | None = None, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    statement = select(Holiday).order_by(Holiday.event_date).limit(_limit(limit)).offset(max(offset, 0))
    if date_value: statement = statement.where(Holiday.event_date == date_value)
    if start_date: statement = statement.where(Holiday.event_date >= start_date)
    if end_date: statement = statement.where(Holiday.event_date <= end_date)
    if holiday_type: statement = statement.where(Holiday.event_type == holiday_type)
    rows = (await db.execute(statement)).scalars().all()
    return {"items": [{"id": h.id, "date": h.event_date, "name": h.name, "type": h.event_type, "poya_name": h.poya_name, "is_public_holiday": h.is_public_holiday, "confirmation_status": h.confirmation_status, "source_url": h.source_url} for h in rows], "limit": _limit(limit), "offset": offset}

@router.get("/api/v1/calendar/poya-days")
async def poya_days(start_date: date | None = None, end_date: date | None = None, limit: int = 50, db: AsyncSession = Depends(get_db)):
    return await holidays(start_date=start_date, end_date=end_date, holiday_type="poya", limit=limit, db=db)

@router.get("/api/v1/events")
async def events(start_date: date | None = None, end_date: date | None = None, district: int | None = None, event_category: str | None = None, limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    statement = select(TourismEvent).order_by(TourismEvent.start_datetime).limit(_limit(limit)).offset(max(offset, 0))
    if start_date: statement = statement.where(TourismEvent.start_datetime >= datetime.combine(start_date, time.min).astimezone())
    if end_date: statement = statement.where(TourismEvent.start_datetime <= datetime.combine(end_date, time.max).astimezone())
    if district is not None: statement = statement.where(TourismEvent.district_id == district)
    if event_category: statement = statement.where(TourismEvent.category == event_category)
    rows = (await db.execute(statement)).scalars().all()
    return {"items": [{"id": e.id, "title": e.title, "category": e.category, "start_datetime": e.start_datetime, "end_datetime": e.end_datetime, "district_id": e.district_id, "status": e.status, "source_url": e.source_url} for e in rows], "limit": _limit(limit), "offset": offset}

@router.get("/api/v1/events/upcoming")
async def upcoming_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    return await events(start_date=datetime.now().date(), limit=limit, db=db)

@router.get("/api/v1/events/{event_id}")
async def event_by_id(event_id: int, db: AsyncSession = Depends(get_db)):
    event = await db.get(TourismEvent, event_id)
    if not event: raise HTTPException(404, "Event not found")
    return {"id": event.id, "title": event.title, "description": event.description, "status": event.status, "source_url": event.source_url}

@router.get("/api/v1/context/holiday-events")
async def holiday_event_context(visit_datetime: datetime, attraction_id: int | None = None, db: AsyncSession = Depends(get_db)):
    data = await HolidayEventContextService(db).context(visit_datetime, attraction_id)
    return {"visit_datetime": visit_datetime, "attraction_id": attraction_id, **data}
