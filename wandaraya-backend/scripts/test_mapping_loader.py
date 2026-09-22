from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal

from app.models.attraction import Attraction
from app.models.attraction_descriptions import AttractionDescription
from app.models.data_sources import DataSource

from app.knowledge_base.processors.category_activity_mapper import (
    CategoryActivityMapper,
)

from app.knowledge_base.loaders.mapping_loader import (
    MappingLoader,
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

        print("\n============================")
        print("ATTRACTION")
        print("============================")

        print(f"ID: {attraction.id}")
        print(f"Name: {attraction.name}")

        rows = (
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

        for source_name, description in rows:
            if not description:
                continue

            if source_name == "Wikipedia":
                wikipedia_text = description
            elif source_name == "Wikivoyage":
                wikivoyage_text = description

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

        mapping = CategoryActivityMapper.map(
            attraction=attraction_data,
            primary_text=wikipedia_text,
            supporting_text=wikivoyage_text,
        )

        print("\n============================")
        print("CATEGORY MAPPINGS")
        print("============================")

        for category in mapping.categories:
            print(
                f"{category.name} "
                f"| {category.confidence:.2f} "
                f"| primary={category.is_primary}"
            )

        print("\n============================")
        print("ACTIVITY MAPPINGS")
        print("============================")

        for activity in mapping.activities:
            print(
                f"{activity.name} "
                f"| {activity.suitability_score:.2f}"
            )

        load_result = await MappingLoader.load(
            db=db,
            attraction_id=attraction.id,
            mapping=mapping,
        )

        await db.flush()
        await db.commit()

        print("\n============================")
        print("DATABASE RESULT")
        print("============================")

        print(f"Categories created: {load_result.categories_created}")
        print(f"Categories updated: {load_result.categories_updated}")
        print(f"Activities created: {load_result.activities_created}")
        print(f"Activities updated: {load_result.activities_updated}")

        if load_result.missing_categories:
            print("Missing categories:", load_result.missing_categories)

        if load_result.missing_activities:
            print("Missing activities:", load_result.missing_activities)

        print("\nSUCCESS")


if __name__ == "__main__":
    asyncio.run(main())