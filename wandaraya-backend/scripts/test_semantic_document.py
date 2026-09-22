from __future__ import annotations

import asyncio

from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder


async def main():
    async with AsyncSessionLocal() as db:
        document = await AttractionDocumentBuilder.build(db, attraction_id=1)

        print("\n====================================")
        print("SEMANTIC DOCUMENT")
        print("====================================")

        print(f"Attraction ID: {document.attraction_id}")
        print(f"Name: {document.name}")
        print(f"City: {document.city}")
        print(f"District: {document.district}")
        print(f"Province: {document.province}")

        print("\nCategories:")
        for category in document.categories:
            print(f"  - {category}")

        print("\nActivities:")
        for activity in document.activities:
            print(f"  - {activity}")

        print("\n====================================")
        print("FINAL EMBEDDING TEXT")
        print("====================================\n")
        print(document.text)
        print("\n====================================")
        print(f"Character count: {len(document.text)}")
        print("====================================")


if __name__ == "__main__":
    asyncio.run(main())