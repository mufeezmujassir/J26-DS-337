from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams,Distance
from app.knowledge_base.embeddings.embedding_service import EmbeddingResult
from app.knowledge_base.embeddings.document_builder import AttractionSemanticDocument

@dataclass
class IndexingResult:
    attraction_id:int
    collection_name:str
    indexed:bool



class AttractionQdrantIndexer:
    COLLECTION_NAME = 'sri_lanka_attractions'
    VECTOR_SIZE = 1024

    def __init__(
        self,
        url: str = 'http://qdrant:6333',
    ):
        self.client = QdrantClient(url=url)

    def ensure_collection(
        self,
    ) -> None:

        if self.client.collection_exists(
            collection_name=self.COLLECTION_NAME
        ):
            return

        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=VectorParams(
                size=self.VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )

    def index(
            self,
            document:AttractionSemanticDocument,
            embedding:EmbeddingResult,
    )->IndexingResult:
        if(embedding.dimension!=self.VECTOR_SIZE):
            raise ValueError(f"Expected {self.VECTOR_SIZE} dimensions, but found {embedding.dimension}")

        self.ensure_collection()

        payload={
            "attraction_id": document.attraction_id,
            "name": document.name,
            "city": document.city,
            "district": document.district,
            "province": document.province,
            "categories": document.categories,
            "activities": document.activities,
        }

        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                PointStruct(
                    id=document.attraction_id,
                    vector=embedding.vector,
                    payload=payload,
                )
            ],
            wait=True
        )
        return IndexingResult(
            attraction_id=document.attraction_id,
            collection_name=self.COLLECTION_NAME,
            indexed=True,
        )