import asyncio

from app.database import AsyncSessionLocal
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService


async def main():
    async with AsyncSessionLocal() as db:
        document = await AttractionDocumentBuilder.build(
            db=db,
            attraction_id=1,
        )

        print("\n============================")
        print("DOCUMENT")
        print("============================")

        print(f"Attraction: {document.name}")
        print(f"Characters: {len(document.text)}")

        embedding = AttractionEmbeddingService.encode(
            document.text,
        )

        print("\n============================")
        print("EMBEDDING")
        print("============================")

        print(f"Model: {embedding.model_name}")
        print(f"Dimension: {embedding.dimension}")
        print(f"Vector values: {len(embedding.vector)}")
        print("First 10 values:")
        print(embedding.vector[:10])

        print("\nSUCCESS")


if __name__ == "__main__":
    asyncio.run(main())

