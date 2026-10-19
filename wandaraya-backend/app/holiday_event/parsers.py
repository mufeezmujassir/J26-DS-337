"""Deterministic, fixture-friendly parsers for approved public sources."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .schemas import EventRecord, HolidayRecord


_POYA = re.compile(r"(?P<name>[A-Za-z ]+)Full Moon Poya Day", re.I)


def parse_calendar_html(html: str, *, source_url: str, year: int) -> list[HolidayRecord]:
    """Parse only explicit date/name rows; malformed or ambiguous rows are omitted."""
    soup = BeautifulSoup(html, "html.parser")
    records: dict[tuple[str, str], HolidayRecord] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            raw_date, name = cells[0], cells[-1]
            if not name or name.lower() in {"holiday", "observance"}:
                continue
            try:
                parsed = date_parser.parse(f"{raw_date} {year}", dayfirst=True, fuzzy=False).date()
            except (TypeError, ValueError, OverflowError):
                continue
            poya = _POYA.search(name)
            tentative = "expected" in name.lower() or "tentative" in name.lower() or "*" in name
            item = HolidayRecord(
                holiday_date=parsed,
                holiday_name=name.replace("*", "").strip(),
                holiday_type="poya" if poya else "holiday",
                poya_name=poya.group("name").strip() if poya else None,
                is_public_holiday=True,
                is_bank_holiday=True,
                confirmation_status="tentative" if tentative else "unknown",
                source_url=source_url,
            )
            records[(item.holiday_date.isoformat(), item.holiday_name.casefold())] = item
    return list(records.values())


def parse_lankaevents_html(html: str, *, source_url: str) -> list[EventRecord]:
    """Extract visible public event cards without invoking private calendar APIs."""
    soup = BeautifulSoup(html, "html.parser")
    records: dict[str, EventRecord] = {}
    for link in soup.select("a[href]"):
        title = link.get_text(" ", strip=True)
        href = urljoin(source_url, link.get("href", ""))
        if not title or len(title) < 3 or href == source_url:
            continue
        # Stable source identity is URL based; only pages that visibly look like events qualify.
        nearby = link.parent.get_text(" ", strip=True) if link.parent else title
        if not re.search(r"event|202[0-9]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", nearby, re.I):
            continue
        source_id = href.rsplit("/", 1)[-1] or title.casefold()
        records[source_id] = EventRecord(source_event_id=source_id, title=title, source_url=href)
    return list(records.values())
