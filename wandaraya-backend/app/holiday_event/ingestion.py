"""Bounded, source-governed ingestion orchestration for Stage 12.3C."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import func, select

from app.models.holiday_calendar import Holiday
from app.models.holiday_event import TourismEvent

from .repository import HolidayEventRepository
from .http_client import RequestsAsyncClient
from .llm_extraction import extract_with_groq
from .schemas import EventRecord, HolidayRecord
from .source_access import TermsReview, runtime_access_check
from .sources.calendar_sri_lanka import CalendarSriLankaExtractor
from .sources.lanka_events import LankaEventsExtractor

SOURCES = {
    "calendar_sri_lanka": ("Calendar Sri Lanka", "https://calendarsrilanka.com/", "calendar", "annual"),
    "lanka_events": ("LankaEvents", "https://lankaevents.lk/", "event", "daily"),
}
SourceName = Literal["calendar_sri_lanka", "lanka_events"]


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in (
        "records_discovered", "records_parsed", "records_validated", "records_fetched",
        "records_inserted", "records_updated", "records_unchanged", "records_rejected",
    )}


class HolidayEventIngestionService:
    def __init__(self, repository: HolidayEventRepository):
        self.repository = repository

    async def register_sources(self):
        return [await self._source(source_key) for source_key in SOURCES]

    async def _source(self, source_key: SourceName):
        name, url, source_type, frequency = SOURCES[source_key]
        return await self.repository.source(name, url, source_type, frequency)

    async def inspect_access(self, source_name: SourceName, *, terms_review: TermsReview | None, timeout_seconds: float = 20) -> dict:
        async with RequestsAsyncClient(timeout_seconds=timeout_seconds) as client:
            return await runtime_access_check(source_name, SOURCES[source_name][1], client, terms_review=terms_review)

    async def run(self, source_name: SourceName, *, dag_id: str, terms_review: TermsReview | None, execute: bool, event_horizon_months: int = 3, max_event_details: int = 50, enable_llm: bool = False) -> dict:
        if not 0 <= event_horizon_months <= 3:
            raise ValueError("event_horizon_months must be between 0 and 3")
        if not 1 <= max_event_details <= 50:
            raise ValueError("max_event_details must be between 1 and 50")
        counts = _empty_counts()
        access = await self.inspect_access(source_name, terms_review=terms_review)
        if not execute:
            return {"status": "DRY_RUN", "source": source_name, "access": access, "counts": counts, "database_readback": {"holidays": 0, "events": 0}, "postgresql_writes": False, "qdrant_writes": False}

        source = await self._source(source_name)
        source.last_attempt_at = datetime.now(timezone.utc)
        run = await self.repository.start_run(source, dag_id, status="RUNNING")
        if not access["permitted"]:
            status = "ACCESS_BLOCKED"
            await self.repository.finish_run(run, status, counts, access["reason"])
            if execute:
                source.last_error = access["reason"]
            await self.repository.db.commit()
            return {"status": status, "source": source_name, "access": access, "counts": counts, "database_readback": {"holidays": 0, "events": 0}, "postgresql_domain_records_written": False, "ingestion_audit_written": True, "qdrant_writes": False}
        try:

            await self.repository.db.commit()
            if source_name == "calendar_sri_lanka":
                records = await self._ingest_calendar(counts)
                readback = {"holidays": await self._holiday_readback(records), "events": 0}
            else:
                records = await self._ingest_events(source, terms_review, float(access["request_interval_seconds"]), counts, event_horizon_months, max_event_details, enable_llm)
                readback = {"holidays": 0, "events": await self._event_readback(source.id, records)}
            await self.repository.finish_run(run, "SUCCEEDED", counts)
            source.last_success_at, source.last_error = datetime.now(timezone.utc), None
            await self.repository.db.commit()
        except Exception as exc:
            await self.repository.db.rollback()
            failed = await self.repository.db.get(type(run), run.id)
            if failed is None:
                raise RuntimeError(f"ingestion run {run.id} disappeared after rollback") from exc
            counts["records_rejected"] += 1
            await self.repository.finish_run(failed, "FAILED", counts, str(exc))
            failed_source = await self.repository.db.get(type(source), failed.source_id)
            if failed_source is not None:
                failed_source.last_error = str(exc)
            await self.repository.db.commit()
            raise
        return {"status": "SUCCEEDED", "source": source_name, "access": access, "counts": counts, "database_readback": readback, "postgresql_domain_records_written": True, "ingestion_audit_written": True, "qdrant_writes": False}

    async def _ingest_calendar(self, counts: dict[str, int]) -> list[HolidayRecord]:
        async with RequestsAsyncClient(timeout_seconds=30) as client:
            result = await CalendarSriLankaExtractor().fetch_current_page(client)
        records = CalendarSriLankaExtractor().parse(result, datetime.now().year)
        counts.update(records_discovered=len(records), records_parsed=len(records), records_validated=len(records), records_fetched=1)
        for record in records:
            counts[f"records_{await self.repository.upsert_holiday(None, record)}"] += 1
        return records

    async def _ingest_events(self, source, terms_review: TermsReview | None, request_interval_seconds: float, counts: dict[str, int], event_horizon_months: int, max_event_details: int, enable_llm: bool) -> list[EventRecord]:
        # Browser-observed internal endpoints are never called. Only detail URL
        # path prefixes recorded in the source terms review can be requested.
        async with RequestsAsyncClient(timeout_seconds=30) as client:
            listing = await LankaEventsExtractor().fetch_public_listing(client)
            extractor = LankaEventsExtractor()
            discovered = extractor.parse(listing)
            prefixes = terms_review.allowed_detail_path_prefixes if terms_review else ()
            unique_candidates = {item.source_event_id: item for item in discovered}
            candidates = [item for item in unique_candidates.values() if self._is_permitted_detail_url(item.source_url, prefixes)][:max_event_details]
            records: list[EventRecord] = []
            for candidate in candidates:
                await asyncio.sleep(request_interval_seconds)
                fetched = await extractor.fetch_public_detail(client, candidate.source_url)
                detail = extractor.parse_detail(fetched)
                if detail and enable_llm and (not detail.description or detail.start_datetime is None or not detail.venue):
                    detail = await self._apply_llm_fallback(detail, fetched.html)
                if detail and self._within_horizon(detail, event_horizon_months):
                    records.append(detail)
        counts.update(records_discovered=len(unique_candidates), records_parsed=len(candidates), records_validated=len(records), records_fetched=1 + len(candidates), records_rejected=len(candidates) - len(records))
        for record in records:
            counts[f"records_{await self.repository.upsert_event(source, record)}"] += 1
        return records

    @staticmethod
    async def _apply_llm_fallback(record: EventRecord, html: str) -> EventRecord:
        """Fill only absent non-identity fields with evidence-bound LLM output."""
        result = await extract_with_groq(html, enabled=True)
        if result.status != "LLM_EXTRACTION_AVAILABLE" or not result.accepted_fields:
            return record
        updates: dict[str, object] = {"extraction_method": "llm_assisted", "extraction_confidence": 0.6, "extraction_evidence": result.accepted_fields}
        mapping = {"description": "description", "venue": "venue", "city": "city", "province": "province", "organizer": "organizer", "category": "original_category", "ticket_information": "price_information", "registration_url": "registration_url"}
        current = record.model_dump()
        for llm_field, model_field in mapping.items():
            if not current.get(model_field) and result.accepted_fields.get(llm_field):
                updates[model_field] = result.accepted_fields[llm_field]
        return record.model_copy(update=updates)

    @staticmethod
    def _is_permitted_detail_url(url: str, prefixes: tuple[str, ...]) -> bool:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in {"lankaevents.lk", "www.lankaevents.lk"} and any(parsed.path.startswith(prefix) for prefix in prefixes)

    @staticmethod
    def _within_horizon(record: EventRecord, horizon_months: int) -> bool:
        if record.start_datetime is None:
            return False
        now = datetime.now(record.start_datetime.tzinfo or timezone.utc)
        latest_month = now.month + horizon_months
        latest_year = now.year + (latest_month - 1) // 12
        latest_month = ((latest_month - 1) % 12) + 1
        return record.end_datetime is None or record.end_datetime >= now and (record.start_datetime.year, record.start_datetime.month) <= (latest_year, latest_month)

    async def _holiday_readback(self, records: list[HolidayRecord]) -> int:
        if not records:
            return 0
        return int(await self.repository.db.scalar(select(func.count()).select_from(Holiday).where(Holiday.source_url == records[0].source_url)) or 0)

    async def _event_readback(self, source_id: int, records: list[EventRecord]) -> int:
        if not records:
            return 0
        return int(await self.repository.db.scalar(select(func.count()).select_from(TourismEvent).where(TourismEvent.source_id == source_id, TourismEvent.source_event_id.in_([item.source_event_id for item in records]))) or 0)
