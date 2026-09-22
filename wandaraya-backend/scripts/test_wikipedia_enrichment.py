from __future__ import annotations
from datetime import datetime
import asyncio
from sqlalchemy import func,select
from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from app.knowledge_base.enrichment.wikipedia_enricher import WikipediaEnricher

async def main():
    async with AsyncSessionLocal() as db:
        try:
            statement=(select(Attraction).where(
                Attraction.google_place_id=="ChIJXQLueKNz4ToR_sMWrhaKb7k"
            )).limit(1)

            result = await db.execute(statement)
            attraction = result.scalars().first()

            if attraction is None:
                print( "Galle Dutch Fort is not "
                    "stored in attractions.")
                return

            
            print("\n============================")
            print("ATTRACTION")
            print("============================")

            print(
                f"ID: {attraction.id}"
            )

            print(
                f"Name: {attraction.name}"
            )

            print(
                f"City: {attraction.city}"
            )

            
            enricher = WikipediaEnricher()

            description = (
                await enricher.enrich(
                    db=db,
                    attraction=attraction,
                )
            )

            if description is None:

                print("\n============================")
                print("NO MATCH")
                print("============================")

                print(
                    "No sufficiently safe Wikipedia "
                    "match was found."
                )

                return

            

            await db.commit()

            await db.refresh(
                description
            )

            print("\n============================")
            print("WIKIPEDIA ENRICHMENT")
            print("============================")

            print(
                f"Description ID: "
                f"{description.id}"
            )

            print(
                f"Attraction ID: "
                f"{description.attraction_id}"
            )

            print(
                f"Source ID: "
                f"{description.source_id}"
            )

            print(
                f"Title: "
                f"{description.title}"
            )

            print(
                f"Language: "
                f"{description.language}"
            )

            print(
                f"URL: "
                f"{description.source_url}"
            )

            print(
                f"Hash: "
                f"{description.content_hash}"
            )

            print("\nPreview:")

            print(
                (
                    description.description
                    or ""
                )[:1000]
            )

            print(
                "\nSUCCESS"
            )

        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())