from app.database import AsyncSessionLocal
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever
import asyncio

TEST_QUERIES = [
    "historical heritage place in Galle",

    "Dutch colonial historical attraction",

    "ancient archaeological site in Sri Lanka",

    "wildlife safari with elephants",

    "Buddhist religious and cultural attraction",

    "beach destination near the ocean",
]

async def main() -> None:
    db = AsyncSessionLocal()
    try:
        retriever = SemanticAttractionRetriever()

        for query in TEST_QUERIES:


            print("\n================================")
            print("Query:")
            print("================================")
            print(query)

            candidates = await retriever.search(
                db=db,
                query=query,
                limit=5,
            )

            print("\nRESULTS")
            print("--------------------------------")

            if not candidates:
                print("No results found.")
                continue

            for rank, candidate in enumerate(
                candidates,
                start=1,
            ):
                print(
                    f"{rank}. "
                    f"{candidate.name}"
                )

                print(
                    f"   Attraction ID: "
                    f"{candidate.attraction_id}"
                )

                print(
                    f"   Score: "
                    f"{candidate.score:.4f}"
                )

                print(
                    f"   City: "
                    f"{candidate.city}"
                )
    finally:
        await db.close()

if  __name__ == "__main__":

    asyncio.run(main())

