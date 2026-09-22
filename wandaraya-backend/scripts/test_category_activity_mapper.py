from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal

from app.models.attraction import Attraction
from app.models.attraction_descriptions import (
    AttractionDescription,
)
from app.models.data_sources import DataSource

from app.knowledge_base.processors.category_activity_mapper import (
    CategoryActivityMapper,
)


async def main():

    async with AsyncSessionLocal() as db:
        attraction_result = await db.execute(
            select(Attraction)
            .where(
                Attraction.id == 1
            )
        )
        attraction = attraction_result.scalars().first()

        if attraction is None:
            print("Attraction not found.")
            return

        description_rows = (
            await db.execute(
                select(
                    DataSource.name,
                    AttractionDescription.description,
                )
                .join(
                    DataSource,
                    AttractionDescription.source_id
                    == DataSource.id,
                )
                .where(
                    AttractionDescription.attraction_id
                    == attraction.id,
                    AttractionDescription.is_active
                    == True,
                )
            )
        ).all()

        wikipedia_text = ""
        wikivoyage_text = ""

        for source_name, description in description_rows:

            if not description:
                continue

            if source_name == "Wikipedia":
                wikipedia_text = description

            elif source_name == "Wikivoyage":
                wikivoyage_text = description

        # For this test we know these came from
        # Google Places for Galle Dutch Fort.
        attraction_data = {

            "name": attraction.name,

            "source_metadata": {
                "types": [
                    "historical_landmark",
                    "historical_place",
                    "tourist_attraction",
                    "point_of_interest",
                    "establishment",
                ]
            },
        }

        result = CategoryActivityMapper.map(
            attraction=attraction_data,
            primary_text=wikipedia_text,
            supporting_text=wikivoyage_text,
        )

        print("\n============================")
        print("ATTRACTION")
        print("============================")

        print(attraction.name)

        print("\n============================")
        print("CATEGORIES")
        print("============================")

        if not result.categories:
            print("None")

        for category in result.categories:

            print(
                f"{category.name} "
                f"| confidence="
                f"{category.confidence:.2f} "
                f"| primary="
                f"{category.is_primary}"
            )

        print("\n============================")
        print("ACTIVITIES")
        print("============================")

        if not result.activities:
            print("None")

        for activity in result.activities:

            print(
                f"{activity.name} "
                f"| suitability="
                f"{activity.suitability_score:.2f}"
            )


if __name__ == "__main__":
    asyncio.run(main())