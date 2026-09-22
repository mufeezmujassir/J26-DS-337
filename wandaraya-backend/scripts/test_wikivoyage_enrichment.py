from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.knowledge_base.enrichment.wikivoyage_enricher import WikivoyageEnricher
from app.models.attraction import Attraction


PLACE_ID = "ChIJXQLueKNz4ToR_sMWrhaKb7k"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Attraction)
                .where(Attraction.google_place_id == PLACE_ID)
                .limit(1)
            )
            attraction = result.scalars().first()

            if attraction is None:
                print("Attraction not found.")
                return

            print("\n============================")
            print("ATTRACTION")
            print("============================")
            print(f"ID: {attraction.id}")
            print(f"Name: {attraction.name}")
            print(f"City: {attraction.city}")

            description = await WikivoyageEnricher().enrich(
                db=db,
                attraction=attraction,
            )
            if description is None:
                print("\n============================")
                print("NO WIKIVOYAGE MATCH")
                print("============================")
                print("No sufficiently safe Wikivoyage content was found.")
                return

            await db.commit()
            await db.refresh(description)

            print("\n============================")
            print("WIKIVOYAGE ENRICHMENT")
            print("============================")
            print(f"Description ID: {description.id}")
            print(f"Attraction ID: {description.attraction_id}")
            print(f"Source ID: {description.source_id}")
            print(f"Title: {description.title}")
            print(f"Language: {description.language}")
            print(f"URL: {description.source_url}")
            print(f"Hash: {description.content_hash}")
            print("\nRelevant Content:")
            print((description.description or "")[:1500])
            print("\nSUCCESS")
        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
