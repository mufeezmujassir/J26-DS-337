"""Transactional persistence for approved holiday/event source records."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday_calendar import Holiday
from app.models.holiday_event import IngestionRun, IngestionSource, HolidayEventRevision, TourismEvent

from .schemas import EventRecord, HolidayRecord


def now() -> datetime: return datetime.now(timezone.utc)


class HolidayEventRepository:
    def __init__(self, db: AsyncSession): self.db = db

    async def source(self, name: str, url: str, source_type: str, frequency: str) -> IngestionSource:
        item = (await self.db.execute(select(IngestionSource).where(IngestionSource.source_name == name))).scalar_one_or_none()
        if item is None:
            item = IngestionSource(source_name=name, base_url=url, source_type=source_type, ingestion_frequency=frequency)
            self.db.add(item); await self.db.flush()
        return item

    async def start_run(self, source: IngestionSource, dag_id: str, status: str = "RUNNING") -> IngestionRun:
        run = IngestionRun(source_id=source.id, dag_id=dag_id, status=status); self.db.add(run); await self.db.flush(); return run

    async def finish_run(self, run: IngestionRun, status: str, counts: dict, error: str | None = None) -> None:
        run.status, run.finished_at, run.error_summary = status, now(), error
        for field in ("records_fetched", "records_inserted", "records_updated", "records_unchanged", "records_rejected"):
            setattr(run, field, int(counts.get(field, 0)))

    async def upsert_holiday(self, source_id: int | None, record: HolidayRecord) -> str:
        item = (await self.db.execute(select(Holiday).where(Holiday.event_date == record.holiday_date, Holiday.name == record.holiday_name, Holiday.source_url == record.source_url))).scalar_one_or_none()
        values = {"event_type": record.holiday_type, "poya_name": record.poya_name, "religious_category": record.religious_category, "is_poya": bool(record.poya_name), "is_public_holiday": record.is_public_holiday, "is_bank_holiday": record.is_bank_holiday, "is_mercantile_holiday": record.is_mercantile_holiday, "confirmation_status": record.confirmation_status, "source_updated_at": record.source_updated_at, "last_seen_at": now()}
        if item is None:
            self.db.add(Holiday(event_date=record.holiday_date, name=record.holiday_name, source_id=source_id, source_url=record.source_url, first_seen_at=now(), **values)); return "inserted"
        changed = {key: value for key, value in values.items() if getattr(item, key) != value}
        if not changed: return "unchanged"
        self.db.add(HolidayEventRevision(record_type="holiday", record_identifier=str(item.id), previous_values={k: getattr(item, k) for k in changed}, updated_values=changed, source_evidence=record.source_url, change_reason="source_update"))
        for key, value in changed.items(): setattr(item, key, value)
        return "updated"

    async def upsert_event(self, source: IngestionSource, record: EventRecord) -> str:
        item = (await self.db.execute(select(TourismEvent).where(TourismEvent.source_id == source.id, TourismEvent.source_event_id == record.source_event_id))).scalar_one_or_none()
        values = record.model_dump(exclude={"source_event_id"}); values["last_seen_at"] = now()
        if item is None:
            self.db.add(TourismEvent(source_id=source.id, source_event_id=record.source_event_id, first_seen_at=now(), **values)); return "inserted"
        changed = {key: value for key, value in values.items() if getattr(item, key) != value}
        if not changed: return "unchanged"
        self.db.add(HolidayEventRevision(record_type="event", record_identifier=str(item.id), previous_values={k: getattr(item, k) for k in changed}, updated_values=changed, source_evidence=record.source_url, change_reason="source_update"))
        for key, value in changed.items(): setattr(item, key, value)
        return "updated"
