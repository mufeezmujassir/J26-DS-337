"""Deterministic, fixture-friendly parsers for approved public sources."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .schemas import EventRecord, HolidayRecord


_POYA = re.compile(r"(?P<name>[A-Za-z ]+)Full Moon Poya Day", re.I)


def _religious_category(name: str, poya: re.Match[str] | None) -> str | None:
    lowered = name.casefold()
    if poya:
        return "buddhist"
    if any(term in lowered for term in ("eid", "ramadan", "milad", "haj")):
        return "islamic"
    if any(term in lowered for term in ("christmas", "good friday", "easter")):
        return "christian"
    if any(term in lowered for term in ("pongal", "deepavali", "shivaratri")):
        return "hindu"
    return None


def parse_calendar_html(html: str, *, source_url: str, year: int) -> list[HolidayRecord]:
    """Parse only explicit date/name rows; malformed or ambiguous rows are omitted."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True).casefold()
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
                religious_category=_religious_category(name, poya),
                is_public_holiday="public holiday" in page_text,
                is_bank_holiday=True if "bank holiday" in page_text else None,
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


def _label_value(soup: BeautifulSoup, label: str) -> str | None:
    """Read visible label/value pairs without relying on implementation endpoints."""
    expression = re.compile(rf"^\s*{re.escape(label)}\s*:?[\s]*$", re.I)
    node = soup.find(string=expression)
    if node is None:
        return None
    parent = node.parent
    sibling = parent.find_next_sibling() if parent else None
    value = (sibling or parent).get_text(" ", strip=True) if (sibling or parent) else None
    if value and value.casefold() != label.casefold():
        return re.sub(rf"^{re.escape(label)}\s*:?[\s]*", "", value, flags=re.I).strip() or None
    combined = parent.parent.get_text(" ", strip=True) if parent and parent.parent else ""
    match = re.search(rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:Venue|Date|Time|Organizer|Notes)\s*:|$)", combined, re.I)
    return match.group(1).strip() if match else None


def _parse_event_datetime(value: str | None, *, default_year: int | None = None) -> tuple[datetime | None, datetime | None]:
    if not value:
        return None, None
    cleaned = re.sub(r"\s+", " ", value).strip()
    parts = re.split(r"\s+(?:-|–|to)\s+", cleaned, maxsplit=1)
    try:
        start = date_parser.parse(parts[0], dayfirst=True, default=datetime(default_year or datetime.now().year, 1, 1))
        end = date_parser.parse(parts[1], dayfirst=True, default=start) if len(parts) == 2 else start
    except (TypeError, ValueError, OverflowError):
        return None, None
    tz = ZoneInfo("Asia/Colombo")
    return start.replace(tzinfo=tz), end.replace(tzinfo=tz)


def parse_lankaevents_detail_html(html: str, *, source_url: str) -> EventRecord | None:
    """Parse an already-authorized, public event-detail page.

    This intentionally accepts HTML supplied by the fetcher/fixture only.  It
    does not discover or call browser-observed internal AJAX endpoints.
    """
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1, .event-title, .title") or soup.find("title")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title:
        return None
    raw_dates = _label_value(soup, "Date")
    raw_times = _label_value(soup, "Time")
    start, end = _parse_event_datetime(raw_dates)
    if raw_times and start:
        time_parts = re.split(r"\s+(?:-|–|to)\s+", raw_times, maxsplit=1)
        try:
            start_time = date_parser.parse(time_parts[0]).timetz().replace(tzinfo=None)
            start = start.replace(hour=start_time.hour, minute=start_time.minute, second=0)
            if len(time_parts) == 2:
                end_time = date_parser.parse(time_parts[1]).timetz().replace(tzinfo=None)
                end = (end or start).replace(hour=end_time.hour, minute=end_time.minute, second=0)
        except (TypeError, ValueError, OverflowError):
            pass
    notes = _label_value(soup, "Notes")
    all_text = soup.get_text(" ", strip=True)
    hashtags = sorted(set(re.findall(r"#[\w-]+", all_text)))
    source_id_match = re.search(r"(?:[?&]id=|/)(\d+)(?:\D*$|$)", source_url)
    source_event_id = source_id_match.group(1) if source_id_match else source_url.rstrip("/").rsplit("/", 1)[-1]
    return EventRecord(
        source_event_id=source_event_id,
        title=title,
        description=notes,
        start_datetime=start,
        end_datetime=end,
        venue=_label_value(soup, "Venue"),
        organizer=_label_value(soup, "Organizer"),
        event_notes=notes,
        hashtags=hashtags,
        source_url=source_url,
        event_url=source_url,
        status="scheduled" if start else "unknown",
    )
