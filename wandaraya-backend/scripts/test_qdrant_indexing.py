from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.knowledge_base.embeddings.document_builder import AttractionDocumentBuilder
from app.knowledge_base.embeddings.qdrant_indexer import AttractionQdrantIndexer
from app.database import AsyncSessionLocal
 
import asyncio
async def main():
    async with AsyncSessionLocal() as db:
        try:
            print("\n================")
            print("BUILDING DOCUMENTS")
            print("================\n")

            document = await AttractionDocumentBuilder.build(db, attraction_id=1)

            print("\n================")
            print("BUILDING EMBEDDING")
            print("================\n")

            embedding = AttractionEmbeddingService.encode(document.text)

            print("\n================")
            print("INDEXING DOCUMENT")
            print("================\n")

            indexer = AttractionQdrantIndexer()

            result = indexer.index(document=document, embedding=embedding)

            print(
            f"Attraction ID: "
            f"{result.attraction_id}"
            )

            print(
                f"Collection: "
                f"{result.collection_name}"
            )

            print(
                f"Indexed: "
                f"{result.indexed}"
            )

            print("\nSUCCESS")
        finally:
            await db.close()

if __name__ == "__main__":
    asyncio.run(main())
    