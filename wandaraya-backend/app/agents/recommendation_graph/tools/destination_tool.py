from __future__ import annotations

import re

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.models.district import District


class DestinationToolInput(BaseModel):
    destination_text: str = Field(min_length=2, max_length=120)


async def resolve_destination(db: AsyncSession, destination_text: str) -> dict:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", destination_text.casefold()).split())
    exact = (await db.execute(select(District).where(
        District.is_active.is_(True), func.lower(District.name) == normalized
    ))).scalars().all()
    if len(exact) == 1:
        item = exact[0]
        return {"status": "RESOLVED", "district_id": item.id, "district_name": item.name, "resolution": "district_exact"}

    # Natural requests commonly contain qualifiers such as "southern province",
    # "near", or "area". Resolve an unambiguous verified district mentioned as
    # a complete phrase instead of requiring the whole input to equal its name.
    districts = (await db.execute(
        select(District).where(District.is_active.is_(True)).order_by(District.name)
    )).scalars().all()
    district_mentions = [
        item for item in districts
        if re.search(
            rf"(?:^|\s){re.escape(' '.join(re.sub(r'[^a-z0-9]+', ' ', item.name.casefold()).split()))}(?:$|\s)",
            normalized,
        )
    ]
    if len(district_mentions) == 1:
        item = district_mentions[0]
        return {
            "status": "RESOLVED", "district_id": item.id,
            "district_name": item.name, "resolution": "district_mentioned_in_phrase",
        }
    if len(district_mentions) > 1:
        return {
            "status": "AMBIGUOUS",
            "candidates": [{"id": item.id, "name": item.name} for item in district_mentions],
            "message": f"'{destination_text}' mentions multiple districts.",
        }

    province_mentions = sorted({
        item.province for item in districts
        if re.search(
            rf"(?:^|\s){re.escape(' '.join(re.sub(r'[^a-z0-9]+', ' ', item.province.casefold()).split()))}(?:$|\s)",
            normalized,
        )
    })
    if len(province_mentions) == 1:
        province = province_mentions[0]
        candidates = [item for item in districts if item.province == province]
        return {
            "status": "AMBIGUOUS",
            "candidates": [{"id": item.id, "name": item.name} for item in candidates],
            "message": (
                f"'{destination_text}' identifies {province} Province. "
                f"Choose a district: {', '.join(item.name for item in candidates)}."
            ),
        }

    city_rows = (await db.execute(
        select(Attraction.district_id).where(
            Attraction.is_active.is_(True), Attraction.district_id.is_not(None),
            func.lower(Attraction.city) == normalized,
        ).distinct()
    )).scalars().all()
    city_ids = sorted(set(city_rows))
    if len(city_ids) == 1:
        district = await db.get(District, city_ids[0])
        return {"status": "RESOLVED", "district_id": district.id, "district_name": district.name,
                "resolution": "verified_attraction_city_to_district", "city": destination_text.strip()}
    if len(city_ids) > 1:
        return {"status": "AMBIGUOUS", "candidates": city_ids,
                "message": f"'{destination_text}' maps to attractions in multiple districts."}

    partial = (await db.execute(select(District).where(
        District.is_active.is_(True), func.lower(District.name).contains(normalized)
    ).order_by(District.name).limit(6))).scalars().all()
    if len(partial) == 1:
        item = partial[0]
        return {"status": "RESOLVED", "district_id": item.id, "district_name": item.name, "resolution": "district_unique_partial"}
    if partial:
        return {"status": "AMBIGUOUS", "candidates": [{"id": x.id, "name": x.name} for x in partial],
                "message": f"'{destination_text}' matches multiple districts."}
    return {"status": "NOT_FOUND", "message": f"No verified district or attraction city matched '{destination_text}'."}


def build_destination_tool(db: AsyncSession) -> StructuredTool:
    async def _run(destination_text: str) -> dict:
        return await resolve_destination(db, destination_text)

    return StructuredTool.from_function(
        coroutine=_run,
        name="resolve_sri_lanka_destination",
        description="Resolve a user-supplied Sri Lankan destination to a verified district using parameterized database queries.",
        args_schema=DestinationToolInput,
    )
