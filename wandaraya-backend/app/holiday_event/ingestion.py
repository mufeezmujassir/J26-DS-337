"""Access-gated orchestration; parsing and persistence remain independently testable."""
from __future__ import annotations
from .repository import HolidayEventRepository
from .source_access import check_source_access

SOURCES = {"calendar_sri_lanka": ("Calendar Sri Lanka", "https://calendarsrilanka.com/", "calendar", "annual"), "lanka_events": ("LankaEvents", "https://lankaevents.lk/", "event", "daily")}

class HolidayEventIngestionService:
    def __init__(self, repository: HolidayEventRepository): self.repository = repository
    async def register_sources(self) -> list[dict]:
        result=[]
        for _, (name, url, kind, frequency) in SOURCES.items():
            source=await self.repository.source(name, url, kind, frequency); result.append({"id":source.id,"source_name":name,"base_url":url,"frequency":frequency})
        return result
    def access_check(self, source_key: str) -> dict:
        _, url, _, _ = SOURCES[source_key]; return check_source_access(source_key, url)
