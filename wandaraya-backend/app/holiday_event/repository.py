"""Transactional persistence for approved holiday/event source records."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from math import isfinite
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday_calendar import Holiday
from app.models.holiday_event import IngestionRun, IngestionSource, HolidayEventRevision, TourismEvent

from .schemas import EventRecord, HolidayRecord


def now() -> datetime: return datetime.now(timezone.utc)


def json_safe(value):
    """Convert only known JSON-adjacent values; reject arbitrary objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("non-finite float cannot be stored in a JSON revision")
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("revision JSON object keys must be strings")
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    raise TypeError(f"unsupported revision JSON value: {type(value).__name__}")


def holiday_source_values(record: HolidayRecord) -> dict:
    """Meaningful source content only; observation timestamps are excluded."""
    values = record.model_dump(mode="python", exclude={"source_url", "source_record_id"})
    return {
        "event_type": values["holiday_type"],
        "description": values["description"],
        "poya_name": values["poya_name"],
        "religious_category": values["religious_category"],
        "is_poya": bool(values["poya_name"]),
        "is_public_holiday": values["is_public_holiday"],
        "is_bank_holiday": values["is_bank_holiday"],
        "is_mercantile_holiday": values["is_mercantile_holiday"],
        "confirmation_status": values["confirmation_status"],
        "source_updated_at": values["source_updated_at"],
    }


def event_source_values(record: EventRecord) -> dict:
    return record.model_dump(mode="python", exclude={"source_event_id"})


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
        values = holiday_source_values(record)
        observed_at = now()
        if item is None:
            self.db.add(Holiday(event_date=record.holiday_date, name=record.holiday_name, source_id=source_id, source_url=record.source_url, first_seen_at=observed_at, last_seen_at=observed_at, **values)); return "inserted"
        changed = {key: value for key, value in values.items() if getattr(item, key) != value}
        item.last_seen_at = observed_at
        if not changed:
            return "unchanged"
        self.db.add(HolidayEventRevision(record_type="holiday", record_identifier=str(item.id), previous_values=json_safe({key: getattr(item, key) for key in changed}), updated_values=json_safe(changed), source_evidence=record.source_url, change_reason="source_content_update"))
        for key, value in changed.items(): setattr(item, key, value)
        return "updated"

    async def upsert_event(self, source: IngestionSource, record: EventRecord) -> str:
        item = (await self.db.execute(select(TourismEvent).where(TourismEvent.source_id == source.id, TourismEvent.source_event_id == record.source_event_id))).scalar_one_or_none()
        values = event_source_values(record)
        observed_at = now()
        if item is None:
            self.db.add(TourismEvent(source_id=source.id, source_event_id=record.source_event_id, first_seen_at=observed_at, last_seen_at=observed_at, **values)); return "inserted"
        changed = {key: value for key, value in values.items() if getattr(item, key) != value}
        item.last_seen_at = observed_at
        if not changed:
            return "unchanged"
        self.db.add(HolidayEventRevision(record_type="event", record_identifier=str(item.id), previous_values=json_safe({key: getattr(item, key) for key in changed}), updated_values=json_safe(changed), source_evidence=record.source_url, change_reason="source_content_update"))
        for key, value in changed.items(): setattr(item, key, value)
        return "updated"
