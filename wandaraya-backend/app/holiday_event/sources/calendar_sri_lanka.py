"""Calendar Sri Lanka extractor. No network activity occurs on import."""
from __future__ import annotations
from dataclasses import dataclass
from app.holiday_event.parsers import parse_calendar_html

@dataclass(frozen=True)
class CalendarFetchResult:
    url: str
    status_code: int
    html: str

class CalendarSriLankaExtractor:
    base_url = "https://calendarsrilanka.com/"
    async def fetch_current_page(self, client) -> CalendarFetchResult:
        response = await client.get(self.base_url)
        response.raise_for_status()
        return CalendarFetchResult(str(response.url), response.status_code, response.text)
    def parse(self, result: CalendarFetchResult, year: int):
        return parse_calendar_html(result.html, source_url=result.url, year=year)
