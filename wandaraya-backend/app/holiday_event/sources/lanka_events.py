"""LankaEvents public-page extractor. Private calendar endpoints are excluded."""
from __future__ import annotations
from dataclasses import dataclass
from app.holiday_event.parsers import parse_lankaevents_detail_html, parse_lankaevents_html, parse_lankaevents_icalendar

@dataclass(frozen=True)
class EventFetchResult:
    url: str
    status_code: int
    html: str

class LankaEventsExtractor:
    base_url = "https://lankaevents.lk/"
    async def fetch_public_listing(self, client) -> EventFetchResult:
        response = await client.get(self.base_url)
        response.raise_for_status()
        return EventFetchResult(str(response.url), response.status_code, response.text)
    async def fetch_public_detail(self, client, url: str) -> EventFetchResult:
        response = await client.get(url)
        response.raise_for_status()
        return EventFetchResult(str(response.url), response.status_code, response.text)
    def parse(self, result: EventFetchResult):
        return parse_lankaevents_html(result.html, source_url=result.url)
    def parse_detail(self, result: EventFetchResult):
        if "BEGIN:VCALENDAR" in result.html.upper():
            return parse_lankaevents_icalendar(result.html, source_url=result.url)
        return parse_lankaevents_detail_html(result.html, source_url=result.url)
