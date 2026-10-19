"""Idempotently register approved source definitions; no HTTP calls occur."""
import asyncio
import json

from app.database import AsyncSessionLocal
from app.holiday_event.ingestion import HolidayEventIngestionService
from app.holiday_event.repository import HolidayEventRepository


async def main() -> None:
    async with AsyncSessionLocal() as db:
        records = await HolidayEventIngestionService(HolidayEventRepository(db)).register_sources()
        await db.commit()
    print(json.dumps({"status": "SOURCE_DEFINITIONS_REGISTERED", "records": records, "http_requests": 0}, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
