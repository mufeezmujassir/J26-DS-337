from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activities import Activity


class ActivityToolInput(BaseModel):
    activity_terms: list[str] = Field(default_factory=list, max_length=20)


ALIASES = {
    "cultural sightseeing": ["Cultural Experience", "Temple Visit", "Sightseeing"],
    "scenic sightseeing": ["Sightseeing", "Photography"],
    "nature sightseeing": ["Sightseeing", "Hiking"],
    "beach": ["Beach Relaxation", "Swimming"],
    "wildlife": ["Wildlife Safari", "Bird Watching"],
    "waterfall": ["Sightseeing", "Hiking"],
}


async def resolve_activity(db: AsyncSession, activity_terms: list[str]) -> dict:
    if not activity_terms:
        return {"status": "NOT_REQUESTED", "activity_type_id": None}
    requested_names: list[str] = []
    for term in activity_terms:
        requested_names.extend(ALIASES.get(term.casefold().strip(), [term.strip()]))
    for name in dict.fromkeys(requested_names):
        row = (await db.execute(select(Activity).where(
            Activity.is_active.is_(True), func.lower(Activity.name) == name.casefold()
        ))).scalar_one_or_none()
        if row is not None:
            return {"status": "RESOLVED", "activity_type_id": row.id,
                    "activity_name": row.name, "requested_terms": activity_terms}
    return {"status": "UNSUPPORTED", "activity_type_id": None,
            "message": "No requested activity matched the active activity taxonomy.",
            "requested_terms": activity_terms}


def build_activity_tool(db: AsyncSession) -> StructuredTool:
    async def _run(activity_terms: list[str]) -> dict:
        return await resolve_activity(db, activity_terms)

    return StructuredTool.from_function(
        coroutine=_run,
        name="resolve_tourism_activity",
        description="Resolve requested activities against the active WANDARAYA activity taxonomy.",
        args_schema=ActivityToolInput,
    )
