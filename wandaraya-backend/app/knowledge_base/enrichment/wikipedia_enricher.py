from __future__ import annotations
import hashlib
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.models.attraction_images import AttractionImage
from app.models.attraction_descriptions import AttractionDescription
from app.models.data_sources import DataSource

from app.knowledge_base.connectors.wikipedia import WikipediaConnector


class WikipediaEnricher:
    SOURCE_NAME = "Wikipedia"

    def __init__(self)->None:
        self.connector = WikipediaConnector()

    async def enrich(
            self,
            db:AsyncSession,
            attraction:Attraction,
    )->Optional[AttractionDescription]:
        query=self._build_query(attraction)

        results=await self.connector.search(query=query,limit=5)

        if not results:
            return None

        candidate=self._select_candidate(
            attraction=attraction,
            results=results
        )

        if candidate is None:
            return None

        title = candidate.get("title")

        if not title:
            return None


        page = await self.connector.get_page_extract(
            title=title
        )

        if not page:
            return None

        description = page.get(
            "description"
        )

        if not description:
            return None

        

        source = await self._get_source(
            db
        )

        if source is None:
            raise RuntimeError(
                "Wikipedia data source is not "
                "registered in data_sources."
            )

      

        content_hash = (
            self._generate_hash(
                description
            )
        )

       
        existing = (
            await self._find_existing(
                db=db,
                attraction_id=attraction.id,
                source_id=source.id,
            )
        )

        now = datetime.now(
            timezone.utc
        )

        if existing:

            if (
                existing.content_hash
                == content_hash
            ):

                existing.retrieved_at = now

                return existing

            existing.title = page.get(
                "title"
            )

            existing.description = (
                description
            )

            existing.source_url = (
                page.get("source_url")
            )

            existing.language = (
                page.get(
                    "language",
                    "en",
                )
            )

            existing.content_hash = (
                content_hash
            )

            existing.retrieved_at = now
            existing.is_active = True

            return existing



        record = AttractionDescription(
            attraction_id=attraction.id,
            source_id=source.id,
            title=page.get("title"),
            description=description,
            source_url=page.get(
                "source_url"
            ),
            language=page.get(
                "language",
                "en",
            ),
            content_hash=content_hash,
            retrieved_at=now,
            is_active=True,
        )

        db.add(record)

        return record

  

    @staticmethod
    def _build_query(
        attraction: Attraction,
    ) -> str:

        parts = [
            attraction.name,
        ]

        if attraction.city:
            parts.append(
                attraction.city
            )

        parts.append(
            "Sri Lanka"
        )

        return " ".join(
            dict.fromkeys(parts)
        )

   
    @classmethod
    def _select_candidate(
        cls,
        attraction: Attraction,
        results: list[dict],
    ) -> Optional[dict]:
        """
        Select the safest Wikipedia candidate using attraction-name
        similarity, important name-token overlap, city occurrence,
        and Sri Lanka occurrence.

        This is more flexible than exact-title matching while
        remaining conservative.
        """

        if not results:
            return None

        attraction_name = cls._normalize_text(attraction.name)
        city = cls._normalize_text(attraction.city or "")

        best_candidate = None
        best_score = 0.0

        for result in results:
            title = cls._normalize_text(result.get("title", ""))
            snippet = cls._normalize_text(result.get("snippet", ""))

            if not title:
                continue

            similarity = SequenceMatcher(
                None,
                attraction_name,
                title,
            ).ratio()

            score = similarity * 0.60

            attraction_tokens = set(attraction_name.split())
            title_tokens = set(title.split())

            if attraction_tokens:
                overlap = (
                    len(attraction_tokens & title_tokens)
                    / len(attraction_tokens)
                )
                score += overlap * 0.25

            combined_text = f"{title} {snippet}"

            if city and city in combined_text:
                score += 0.10

            if "sri lanka" in combined_text:
                score += 0.05

            print(
                f"Wikipedia candidate: {result.get('title')} "
                f"| score={score:.3f}"
            )

            if score > best_score:
                best_score = score
                best_candidate = result

        min_score = 0.65

        if best_candidate is None or best_score < min_score:
            return None

        print(
            f"Selected Wikipedia candidate: "
            f"{best_candidate.get('title')} | score={best_score:.3f}"
        )

        return best_candidate

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.strip().casefold().split())


    @classmethod
    async def _get_source(
        cls,
        db: AsyncSession,
    ) -> Optional[DataSource]:

        statement = (
            select(DataSource)
            .where(
                DataSource.name
                == cls.SOURCE_NAME
            )
            .limit(1)
        )

        result = await db.execute(statement)
        return result.scalars().first()


    @staticmethod
    async def _find_existing(
        db: AsyncSession,
        attraction_id: int,
        source_id: int,
    ) -> Optional[AttractionDescription]:

        statement = (
            select(
                AttractionDescription
            )
            .where(
                AttractionDescription.attraction_id
                == attraction_id,

                AttractionDescription.source_id
                == source_id,

                AttractionDescription.language
                == "en",
            )
            .limit(1)
        )

        result = await db.execute(statement)
        return result.scalars().first()

   
    @staticmethod
    def _generate_hash(
        text: str,
    ) -> str:

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
