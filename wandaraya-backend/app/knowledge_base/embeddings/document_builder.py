from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.attraction import Attraction
from app.models.attraction_descriptions import AttractionDescription
from app.models.district import District
from app.models.data_sources import DataSource
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_activities import AttractionActivity
from app.models.categories import Category
from app.models.activities import Activity
from app.database import AsyncSession


@dataclass
class AttractionSemanticDocument:
    attraction_id:int
    text:str

    name:str
    city:str
    district:str
    province:str

    categories:list[str]
    activities:list[str]

    wikipedia_text:str | None
    wikivoyage_text:str|None


class AttractionDocumentBuilder:
    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        attraction_id: int,
    ) -> AttractionSemanticDocument:
        attraction_result = await db.execute(
            select(Attraction).where(
                Attraction.id == attraction_id,
                Attraction.is_active == True,
            )
        )
        attraction = attraction_result.scalars().first()

        if attraction is None:
            raise ValueError(
                f"Active attraction not found: {attraction_id}"
            )

        district_name = None
        province = None

        if attraction.district_id:
            district_result = await db.execute(
                select(District).where(
                    District.id == attraction.district_id,
                )
            )
            district = district_result.scalars().first()

            if district:
                district_name = district.name
                province = district.province

        categories = await cls._get_categories(
            db=db,
            attraction_id=attraction.id,
        )

        activities = await cls._get_activities(
            db=db,
            attraction_id=attraction.id,
        )

        descriptions = await cls._get_descriptions(
            db=db,
            attraction_id=attraction.id,
        )

        wikipedia_text = descriptions.get("Wikipedia")
        wikivoyage_text = descriptions.get("Wikivoyage")

        text = cls._build_text(
            attraction=attraction,
            district=district_name,
            province=province,
            categories=categories,
            activities=activities,
            wikipedia_text=wikipedia_text,
            wikivoyage_text=wikivoyage_text,
        )

        return AttractionSemanticDocument(
            attraction_id=attraction.id,
            text=text,
            name=attraction.name,
            city=attraction.city,
            district=district_name,
            province=province,
            categories=categories,
            activities=activities,
            wikipedia_text=wikipedia_text,
            wikivoyage_text=wikivoyage_text,
        )

    @staticmethod
    async def _get_categories(
        db: AsyncSession,
        attraction_id: int,
    ) -> list[str]:
        rows_result = await db.execute(
            select(Category.name)
            .join(
                AttractionCategory,
                AttractionCategory.category_id == Category.id,
            )
            .where(
                AttractionCategory.attraction_id == attraction_id,
                Category.is_active == True,
            )
            .order_by(
                AttractionCategory.is_primary.desc(),
                AttractionCategory.confidence_score.desc(),
            )
        )

        rows = rows_result.scalars().all()
        return list(rows)

    @staticmethod
    async def _get_activities(
        db: AsyncSession,
        attraction_id: int,
    ) -> list[str]:
        rows_result = await db.execute(
            select(Activity.name)
            .join(
                AttractionActivity,
                AttractionActivity.activity_id == Activity.id,
            )
            .where(
                AttractionActivity.attraction_id == attraction_id,
                AttractionActivity.is_available == True,
                Activity.is_active == True,
            )
            .order_by(
                AttractionActivity.suitability_score.desc()
            )
        )

        rows = rows_result.scalars().all()
        return list(rows)

    @staticmethod
    async def _get_descriptions(
        db: AsyncSession,
        attraction_id: int,
    ) -> dict[str, str]:
        rows_result = await db.execute(
            select(
                DataSource.name,
                AttractionDescription.description,
            )
            .join(
                DataSource,
                AttractionDescription.source_id == DataSource.id,
            )
            .where(
                AttractionDescription.attraction_id == attraction_id,
                AttractionDescription.is_active == True,
            )
        )

        rows = rows_result.all()
        descriptions = {}

        for source_name, description in rows:
            if not description:
                continue
            descriptions[source_name] = description.strip()

        return descriptions

    

    @staticmethod
    def _build_text(
        attraction: Attraction,
        district: str | None,
        province: str | None,
        categories: list[str],
        activities: list[str],
        wikipedia_text: str | None,
        wikivoyage_text: str | None,
    ) -> str:

        sections = []

        sections.append(
            f"Attraction: {attraction.name}"
        )

        location_parts = [
            attraction.city,
            district,
            province,
            "Sri Lanka",
        ]

        # Remove empty + duplicate values.
        clean_location = []

        for item in location_parts:

            if not item:
                continue

            if item not in clean_location:
                clean_location.append(item)

        if clean_location:

            sections.append(
                "Location: "
                + ", ".join(clean_location)
            )

        if categories:

            sections.append(
                "Categories: "
                + ", ".join(categories)
            )

        if activities:

            sections.append(
                "Activities: "
                + ", ".join(activities)
            )

        if wikipedia_text:

            sections.append(
                "Description: "
                + wikipedia_text
            )

        if wikivoyage_text:

            sections.append(
                "Travel context: "
                + wikivoyage_text
            )

        return "\n\n".join(sections)