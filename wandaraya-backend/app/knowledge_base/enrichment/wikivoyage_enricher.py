from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.connectors.wikivoyage import WikivoyageConnector
from app.models.attraction import Attraction
from app.models.attraction_descriptions import AttractionDescription
from app.models.data_sources import DataSource


class WikivoyageEnricher:
    """Enrich attractions with a relevant excerpt from Wikivoyage."""

    SOURCE_NAME = "Wikivoyage"

    def __init__(self) -> None:
        self.connector = WikivoyageConnector()

    async def enrich(
        self,
        db: AsyncSession,
        attraction: Attraction,
    ) -> Optional[AttractionDescription]:
        results = await self.connector.search(
            query=self._build_query(attraction),
            limit=5,
        )

        if not results and attraction.city:
            results = await self.connector.search(
                query=f"{attraction.city} Sri Lanka",
                limit=5,
            )

        candidate = self._select_destination(attraction, results)
        if candidate is None or not (title := candidate.get("title")):
            return None

        page = await self.connector.get_page_extract(title=title)
        if not page or not (page_text := page.get("description") or ""):
            return None

        relevant_text = self._extract_relevant_content(attraction, page_text)
        if not relevant_text:
            print(
                "Wikivoyage destination found, but attraction mention was not "
                "confidently identified."
            )
            return None

        source = await self._get_source(db)
        if source is None:
            raise RuntimeError(
                "Wikivoyage data source is not registered in data_sources."
            )

        content_hash = self._generate_hash(relevant_text)
        existing = await self._find_existing(
            db=db,
            attraction_id=attraction.id,
            source_id=source.id,
        )
        now = datetime.now(timezone.utc)

        if existing:
            if existing.content_hash == content_hash:
                existing.retrieved_at = now
                return existing

            existing.title = page.get("title")
            existing.description = relevant_text
            existing.source_url = page.get("source_url")
            existing.language = page.get("language", "en")
            existing.content_hash = content_hash
            existing.retrieved_at = now
            existing.is_active = True
            return existing

        record = AttractionDescription(
            attraction_id=attraction.id,
            source_id=source.id,
            title=page.get("title"),
            description=relevant_text,
            source_url=page.get("source_url"),
            language=page.get("language", "en"),
            content_hash=content_hash,
            retrieved_at=now,
            is_active=True,
        )
        db.add(record)
        return record

    @staticmethod
    def _build_query(attraction: Attraction) -> str:
        parts = [attraction.name]
        if attraction.city:
            parts.append(attraction.city)
        parts.append("Sri Lanka")
        return " ".join(dict.fromkeys(parts))

    @classmethod
    def _select_destination(
        cls,
        attraction: Attraction,
        results: list[dict],
    ) -> Optional[dict]:
        if not results:
            return None

        city = cls._normalize_text(attraction.city or "")
        attraction_name = cls._normalize_text(attraction.name)
        best_candidate = None
        best_score = 0.0

        for result in results:
            title = cls._normalize_text(result.get("title", ""))
            snippet = cls._normalize_text(result.get("snippet", ""))
            combined = f"{title} {snippet}"
            score = 0.0

            if city and title == city:
                score += 0.70
            elif city and city in title:
                score += 0.50

            if attraction_name and attraction_name in combined:
                score += 0.20
            if "sri lanka" in combined:
                score += 0.10

            print(
                f"Wikivoyage candidate: {result.get('title')} | "
                f"score={score:.3f}"
            )
            if score > best_score:
                best_score = score
                best_candidate = result

        if best_candidate is None or best_score < 0.50:
            return None

        print(
            f"Selected Wikivoyage page: {best_candidate.get('title')} | "
            f"score={best_score:.3f}"
        )
        return best_candidate

    @classmethod
    def _extract_relevant_content(
        cls,
        attraction: Attraction,
        page_text: str,
    ) -> Optional[str]:
        normalized_page = cls._normalize_text(page_text)
        attraction_name = cls._normalize_text(attraction.name)

        if attraction_name and attraction_name in normalized_page:
            return cls._extract_window(page_text, [attraction.name])

        for alias in cls._generate_aliases(attraction.name):
            if cls._normalize_text(alias) in normalized_page:
                return cls._extract_window(page_text, [alias])
        return None

    @staticmethod
    def _generate_aliases(name: str) -> list[str]:
        if "dutch" not in name.casefold():
            return []
        alias = re.sub(r"\bdutch\b", "", name, flags=re.IGNORECASE)
        return [re.sub(r"\s+", " ", alias).strip()]

    @staticmethod
    def _extract_window(
        original_text: str,
        search_terms: list[str],
        window: int = 1200,
    ) -> Optional[str]:
        lowered = original_text.casefold()
        for term in search_terms:
            position = lowered.find(term.casefold())
            if position != -1:
                return original_text[max(0, position - 300):position + window].strip()
        return None

    @classmethod
    async def _get_source(cls, db: AsyncSession) -> Optional[DataSource]:
        result = await db.execute(
            select(DataSource).where(DataSource.name == cls.SOURCE_NAME).limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def _find_existing(
        db: AsyncSession,
        attraction_id: int,
        source_id: int,
    ) -> Optional[AttractionDescription]:
        result = await db.execute(
            select(AttractionDescription)
            .where(
                AttractionDescription.attraction_id == attraction_id,
                AttractionDescription.source_id == source_id,
                AttractionDescription.language == "en",
            )
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = re.sub(r"[^a-z0-9\s]", " ", value.casefold())
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _generate_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
