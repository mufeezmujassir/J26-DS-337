from __future__ import annotations

import random
from collections import defaultdict

from pydantic import BaseModel, Field


class TimingPilotCandidate(BaseModel):
    attraction_id: int = Field(gt=0)
    district_id: int | None = Field(default=None, gt=0)
    category: str | None = None
    managed_status: str = "unknown"
    hours_status: str = "unknown"
    source_status: str = "unknown"
    settlement_context: str | None = None


class PilotSamplingDesign(BaseModel):
    seed: int = Field(ge=0)
    per_stratum: int = Field(gt=0)
    strata_fields: tuple[str, ...] = ("district_id", "category", "managed_status", "hours_status", "source_status")
    limitations: list[str] = Field(default_factory=lambda: ["This is a reproducible pilot design, not a nationally representative sample.", "Settlement context is included only when defensibly supplied; unknown values are retained."])


def select_pilot_sample(candidates: list[TimingPilotCandidate], design: PilotSamplingDesign) -> list[TimingPilotCandidate]:
    """Deterministic offline stratification; never reads or changes the database."""
    buckets: dict[tuple[object, ...], list[TimingPilotCandidate]] = defaultdict(list)
    for candidate in candidates:
        key = tuple(getattr(candidate, field) for field in design.strata_fields)
        buckets[key].append(candidate)
    rng = random.Random(design.seed)
    selected: list[TimingPilotCandidate] = []
    for key in sorted(buckets, key=repr):
        members = sorted(buckets[key], key=lambda item: item.attraction_id)
        rng.shuffle(members)
        selected.extend(members[:design.per_stratum])
    return sorted(selected, key=lambda item: item.attraction_id)
