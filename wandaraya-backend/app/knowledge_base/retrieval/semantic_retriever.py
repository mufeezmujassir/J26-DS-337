from __future__ import annotations

from dataclasses import dataclass
import os

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.knowledge_base.embeddings.embedding_service import AttractionEmbeddingService
from app.models.attraction import Attraction

@dataclass
class SemanticCandidate:
    attraction_id:int
    name:str
    score:float
    city:str
    district_id:int

class SemanticAttractionRetriever:
    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
    ):
        configured_url = (
            url
            or os.getenv("QDRANT_URL")
            or getattr(settings, "QDRANT_URL", "http://qdrant:6333")
            or "http://qdrant:6333"
        )

        if configured_url.startswith("http://localhost") and os.path.exists("/.dockerenv"):
            configured_url = configured_url.replace("localhost", "qdrant", 1)

        self.url = configured_url
        self.collection_name = (
            collection_name
            or os.getenv("QDRANT_COLLECTION_NAME")
            or os.getenv("QDRANT_COLLECTION")
            or "sri_lanka_attractions"
        )
        self.client = QdrantClient(url=self.url)

    async def search(
            self,
            db: AsyncSession,
            query: str,
            limit: int = 10,
    ) -> list[SemanticCandidate]:

        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Query cannot be empty.")

        query_embedding = (
            AttractionEmbeddingService.encode_query(clean_query)
        )

        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:
            raise RuntimeError(
                "Unable to reach Qdrant. Make sure the Docker services are running and "
                f"QDRANT_URL points to the container network address (current: {self.url})."
            ) from exc

        points = response.points

        if not points:
            return []

        scored_ids: list[
            tuple[int, float]
        ] = []

        for point in points:

            payload = point.payload or {}

            attraction_id = payload.get(
                "attraction_id"
            )

            if attraction_id is None:
                continue

            scored_ids.append(
                (
                    int(attraction_id),
                    float(point.score),
                )
            )

        if not scored_ids:
            return []

        attraction_ids = [
            attraction_id
            for attraction_id, _ in scored_ids
        ]

        result = await db.execute(
            select(Attraction)
            .where(
                Attraction.id.in_(attraction_ids),
                Attraction.is_active.is_(True),
            )
        )

        attractions = result.scalars().all()
        attraction_map = {
            attraction.id: attraction
            for attraction in attractions
        }

        candidates = []

        for attraction_id, score in scored_ids:

            attraction = attraction_map.get(
                attraction_id
            )

            if attraction is None:
                continue

            candidates.append(
                SemanticCandidate(
                    attraction_id=attraction.id,
                    name=attraction.name,
                    score=score,
                    city=attraction.city,
                    district_id=attraction.district_id,
                )
            )

        return candidates

        