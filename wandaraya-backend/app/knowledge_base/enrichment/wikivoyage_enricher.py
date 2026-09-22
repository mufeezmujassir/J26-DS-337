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
    MAX_CONTEXT_CHARS = 1200

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
        """Return concise paragraph blocks that are focused on the attraction."""
        if not page_text:
            return None

        aliases = cls._build_aliases(attraction.name)
        text = page_text.replace("\r\n", "\n")
        blocks = re.split(r"\n\s*\n|\n(?=\d+\s)|\n(?=[*#])", text)
        relevant_blocks: list[str] = []

        for block in blocks:
            clean_block = " ".join(block.split()).strip()
            if not clean_block:
                continue

            if not cls._is_relevant_block(clean_block, aliases):
                continue

            relevant_blocks.append(clean_block)

        if not relevant_blocks:
            return None

        unique_blocks: list[str] = []
        seen: set[str] = set()
        for block in relevant_blocks:
            normalized = block.casefold()
            if normalized not in seen:
                seen.add(normalized)
                unique_blocks.append(block)

        return "\n".join(unique_blocks)[: cls.MAX_CONTEXT_CHARS].strip()

    @staticmethod
    def _build_aliases(attraction_name: str) -> list[str]:
        """Return the canonical attraction name plus safe, useful aliases."""
        aliases = {attraction_name.strip()}
        without_dutch = re.sub(
            r"\bdutch\b",
            "",
            attraction_name,
            flags=re.IGNORECASE,
        )
        without_dutch = " ".join(without_dutch.split())
        if without_dutch:
            aliases.add(without_dutch)
        return sorted(aliases, key=len, reverse=True)

    @staticmethod
    def _is_relevant_block(block: str, aliases: list[str]) -> bool:
        """Reject incidental references to an attraction in unrelated listings."""
        normalized_block = block.casefold()
        for alias in aliases:
            normalized_alias = alias.casefold()
            if not normalized_alias:
                continue

            position = normalized_block.find(normalized_alias)
            if position == -1:
                continue

            if position <= 120:
                return True
            if normalized_block.count(normalized_alias) >= 2:
                return True
        return False

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
