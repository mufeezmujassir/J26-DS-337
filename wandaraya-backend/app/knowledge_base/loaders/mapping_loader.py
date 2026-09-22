from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_activities import AttractionActivity
from app.models.categories import Category
from app.models.activities import Activity
from app.knowledge_base.processors.category_activity_mapper import CategoryActivityMapper

@dataclass
class MappingLoadResult:
    categories_created: int = 0
    categories_updated: int = 0
    activities_created: int = 0
    activities_updated: int = 0
    missing_categories: list[str] = None
    missing_activities: list[str] = None

    def __post_init__(self):
        if self.missing_categories is None:
            self.missing_categories = []

        if self.missing_activities is None:
            self.missing_activities = []


class MappingLoader:

    @classmethod
    async def load(
        cls,
        db: AsyncSession,
        attraction_id: int,
        mapping: MappingResult,
    ) -> MappingLoadResult:

        result = MappingLoadResult()

        await cls._load_categories(
            db=db,
            attraction_id=attraction_id,
            mapping=mapping,
            result=result,
        )

        await cls._load_activities(
            db=db,
            attraction_id=attraction_id,
            mapping=mapping,
            result=result,
        )

        return result

    @classmethod
    async def _load_categories(
        cls,
        db: AsyncSession,
        attraction_id: int,
        mapping: MappingResult,
        result: MappingLoadResult,
    ) -> None:

        for category_match in mapping.categories:
            category = await cls._find_category(
                db=db,
                name=category_match.name,
            )

            if category is None:
                result.missing_categories.append(category_match.name)
                continue

            existing_result = await db.execute(
                select(AttractionCategory)
                .where(
                    AttractionCategory.attraction_id == attraction_id,
                    AttractionCategory.category_id == category.id,
                )
            )
            existing = existing_result.scalars().first()

            if existing:
                existing.confidence_score = category_match.confidence
                existing.is_primary = category_match.is_primary
                result.categories_updated += 1
            else:
                relationship = AttractionCategory(
                    attraction_id=attraction_id,
                    category_id=category.id,
                    confidence_score=category_match.confidence,
                    is_primary=category_match.is_primary,
                )
                db.add(relationship)
                result.categories_created += 1

    @classmethod
    async def _load_activities(
        cls,
        db: AsyncSession,
        attraction_id: int,
        mapping: MappingResult,
        result: MappingLoadResult,
    ) -> None:

        for activity_match in mapping.activities:
            activity = await cls._find_activity(
                db=db,
                name=activity_match.name,
            )

            if activity is None:
                result.missing_activities.append(activity_match.name)
                continue

            existing_result = await db.execute(
                select(AttractionActivity)
                .where(
                    AttractionActivity.attraction_id == attraction_id,
                    AttractionActivity.activity_id == activity.id,
                )
            )
            existing = existing_result.scalars().first()

            if existing:
                existing.suitability_score = activity_match.suitability_score
                existing.is_available = True
                result.activities_updated += 1
            else:
                relationship = AttractionActivity(
                    attraction_id=attraction_id,
                    activity_id=activity.id,
                    suitability_score=activity_match.suitability_score,
                    is_available=True,
                )
                db.add(relationship)
                result.activities_created += 1

    @staticmethod
    async def _find_category(
        db: AsyncSession,
        name: str,
    ) -> Category | None:
        result = await db.execute(
            select(Category)
            .where(Category.name == name)
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def _find_activity(
        db: AsyncSession,
        name: str,
    ) -> Activity | None:
        result = await db.execute(
            select(Activity)
            .where(Activity.name == name)
            .limit(1)
        )
        return result.scalars().first()