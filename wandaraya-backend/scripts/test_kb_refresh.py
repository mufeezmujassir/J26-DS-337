from __future__ import annotations

import asyncio

from app.database import AsyncSessionLocal

from app.knowledge_base.refresh.refresh_service import (
    TourismKBRefreshService,
)


TEST_LIMIT = 5


async def main() -> None:

    print()
    print("=" * 70)
    print("WANDARAYA TOURISM KB REFRESH TEST")
    print("=" * 70)

    print(
        f"Refresh limit: {TEST_LIMIT}"
    )

    async with AsyncSessionLocal() as db:

        service = TourismKBRefreshService(
            db=db
        )

        result = await service.refresh(
            limit=TEST_LIMIT
        )

        print()
        print("=" * 70)
        print("REFRESH SUMMARY")
        print("=" * 70)

        print(
            f"Requested:  {result.requested}"
        )

        print(
            f"Successful: {result.successful}"
        )

        print(
            f"Skipped:    {result.skipped}"
        )

        print(
            f"Failed:     {result.failed}"
        )

        print(
            "Attraction IDs: "
            f"{result.refreshed_attraction_ids}"
        )

        if result.errors:

            print()
            print("ERRORS")
            print("-" * 70)

            for error in result.errors:
                print(
                    f"- {error}"
                )

        print("=" * 70)


if __name__ == "__main__":

    asyncio.run(
        main()
    )