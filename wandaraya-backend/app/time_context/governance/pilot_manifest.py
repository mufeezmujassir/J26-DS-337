"""Pure conversion of deterministic sampling output into a planned pilot manifest."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.time_context.governance.sampling import PilotSamplingDesign, TimingPilotCandidate, select_pilot_sample


class PlannedPilotEntry(BaseModel):
    attraction_id: int
    district_id: int | None
    category: str | None
    managed_status: str
    existing_schedule_status: str
    source_status: str
    intended_source: str
    authorization_status: str = "not_authorised_for_fetch_or_persistence"


def build_planned_manifest(candidates: list[TimingPilotCandidate], design: PilotSamplingDesign, *, intended_source: str) -> list[PlannedPilotEntry]:
    """No I/O: callers may serialize the deterministic proposed sample later."""
    return [PlannedPilotEntry(attraction_id=item.attraction_id, district_id=item.district_id,
        category=item.category, managed_status=item.managed_status,
        existing_schedule_status=item.hours_status, source_status=item.source_status,
        intended_source=intended_source) for item in select_pilot_sample(candidates, design)]
