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
_EVENT_CATEGORIES = {
    "drama": "Theatre", "theatre": "Theatre", "music": "Music and Concert",
    "concert": "Music and Concert", "exhibition": "Exhibition", "sport": "Sports",
    "training": "Educational", "course": "Educational", "lecture": "Educational",
    "excursion": "Educational", "conference": "Conference and Seminar",
    "seminar": "Conference and Seminar", "social": "Community", "cultural": "Cultural",
    "festival": "Festival", "religious": "Religious", "food": "Food and Culinary",
    "nature": "Nature and Outdoor", "outdoor": "Nature and Outdoor",
}


def normalize_event_category(value: str | None) -> str | None:
    """Map only explicit source labels into the limited WANDARAYA taxonomy."""
    if not value:
        return None
    lowered = value.casefold()
    for token, normalized in _EVENT_CATEGORIES.items():
        if token in lowered:
            return normalized
    return "Other"


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
        is_icalendar = bool(re.search(r"/iCalendar/\?ID=\d+", href, re.I))
        is_public_detail = bool(re.search(r"/(?:event|events)/", href, re.I))
        if not is_icalendar and not is_public_detail:
            continue
        id_match = re.search(r"[?&]id=(\d+)", href, re.I)
        source_id = id_match.group(1) if id_match else (href.rstrip("/").rsplit("/", 1)[-1] or title.casefold())
        category_node = link.find_parent(attrs={"data-category": True})
        original_category = category_node.get("data-category") if category_node else None
        candidate = EventRecord(source_event_id=source_id, title=title, source_url=href, event_url=href, original_category=original_category, category=normalize_event_category(original_category))
        # The same event can appear on multiple calendar days. Retain the
        # richer visible card rather than letting a later minimal duplicate
        # erase a category discovered on an earlier card.
        previous = records.get(source_id)
        records[source_id] = candidate if previous is None or (candidate.original_category and not previous.original_category) else previous
    return list(records.values())


def parse_lankaevents_icalendar(text: str, *, source_url: str) -> EventRecord | None:
    """Parse a source-provided public iCalendar event without guessing fields."""
    if "BEGIN:VCALENDAR" not in text.upper():
        return None
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    values: dict[str, str] = {}
    for line in unfolded.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.split(";", 1)[0].upper()] = value.strip()
    title = values.get("SUMMARY")
    if not title:
        return None
    def parse_ical(value: str | None) -> datetime | None:
        if not value:
            return None
        raw = value.rstrip("Z")
        for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
            try:
                return datetime.strptime(raw, pattern).replace(tzinfo=ZoneInfo("Asia/Colombo"))
            except ValueError:
                continue
        return None
    event_id = (re.search(r"[?&]ID=(\d+)", source_url, re.I) or re.search(r"[?&]id=(\d+)", source_url, re.I))
    source_id = event_id.group(1) if event_id else source_url.rstrip("/").rsplit("/", 1)[-1]
    category = values.get("CATEGORIES")
    location = values.get("LOCATION")
    description = values.get("DESCRIPTION", "").replace("\\n", "\n") or None
    evidence = {key.lower(): value for key, value in values.items() if key in {"SUMMARY", "DTSTART", "DTEND", "LOCATION", "DESCRIPTION", "CATEGORIES", "ORGANIZER", "URL"}}
    return EventRecord(
        source_event_id=source_id, title=title, description=description,
        original_category=category, category=normalize_event_category(category),
        start_datetime=parse_ical(values.get("DTSTART")), end_datetime=parse_ical(values.get("DTEND")),
        venue=location, organizer=values.get("ORGANIZER"), source_url=source_url,
        event_url=values.get("URL") or source_url, status="scheduled",
        extraction_method="deterministic", extraction_confidence=1.0, extraction_evidence=evidence,
    )


def _label_value(soup: BeautifulSoup, label: str) -> str | None:
    """Read visible label/value pairs without relying on implementation endpoints."""
    expression = re.compile(rf"^\s*{re.escape(label)}\s*:?[\s]*$", re.I)
    node = soup.find(string=expression)
    if node is None:
        node = soup.find(string=re.compile(rf"\b{re.escape(label)}\b\s*:", re.I))
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
    original_category = _label_value(soup, "Category")
    all_text = soup.get_text(" ", strip=True)
    hashtags = sorted(set(re.findall(r"#[\w-]+", all_text)))
    source_id_match = re.search(r"(?:[?&]id=|/)(\d+)(?:\D*$|$)", source_url)
    source_event_id = source_id_match.group(1) if source_id_match else source_url.rstrip("/").rsplit("/", 1)[-1]
    price = _label_value(soup, "Price") or _label_value(soup, "Ticket Price")
    price_text = (price or "").casefold()
    is_free = True if "free" in price_text else (False if price else None)
    currency_match = re.search(r"\b(LKR|Rs\.?|USD|\$)\b", price or "", re.I)
    currency = "LKR" if currency_match and currency_match.group(1).casefold().startswith(("rs", "lkr")) else ("USD" if currency_match else None)
    return EventRecord(
        source_event_id=source_event_id,
        title=title,
        description=notes,
        category=normalize_event_category(original_category),
        original_category=original_category,
        start_datetime=start,
        end_datetime=end,
        venue=_label_value(soup, "Venue"),
        organizer=_label_value(soup, "Organizer"),
        event_notes=notes,
        hashtags=hashtags,
        source_url=source_url,
        event_url=source_url,
        ticket_url=_label_value(soup, "Tickets") or _label_value(soup, "Ticket URL"),
        price_information=price,
        currency=currency,
        is_free=is_free,
        status="scheduled" if start else "unknown",
    )
