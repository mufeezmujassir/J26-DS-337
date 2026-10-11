"""Print the Stage 8 monthly-forecast provider result for a travel date."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from app.database import AsyncSessionLocal
from app.weather_model.context.monthly_forecast_provider import (
    MonthlyForecastProvider,
)


async def main(district_id: int, travel_date: date) -> None:
    """Run a read-only provider lookup and print its structured JSON result."""
    async with AsyncSessionLocal() as db:
        result = await MonthlyForecastProvider.get_monthly_forecast(
            db,
            district_id=district_id,
            travel_date=travel_date,
        )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-id", type=int, required=True)
    parser.add_argument("--travel-date", type=date.fromisoformat, required=True)
    arguments = parser.parse_args()
    asyncio.run(main(arguments.district_id, arguments.travel_date))
