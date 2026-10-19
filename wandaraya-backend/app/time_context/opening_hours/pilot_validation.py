"""Read-only pilot schedule validation for research reporting.

This module never updates attraction data. It is intentionally dataset-size
independent and can be run after future Knowledge Base expansion.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from app.time_context.opening_hours.google_period_parser import (
    normalize_google_regular_opening_hours,
)


async def validate_pilot_schedules(db: AsyncSession) -> dict[str, Any]:
    """Return aggregate parser evidence without exposing attraction records."""
    rows = (await db.execute(
        select(Attraction.id, Attraction.district_id, Attraction.opening_hours)
        .where(Attraction.is_active.is_(True))
        .order_by(Attraction.id)
    )).all()
    status_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    district_coverage: dict[str, dict[str, int]] = {}
    structured_count = missing_close_count = overnight_interval_count = valid_count = 0
    rejected_count = 0

    for attraction_id, district_id, opening_hours in rows:
        is_structured = isinstance(opening_hours, dict)
        structured_count += int(is_structured)
        if is_structured:
            missing_close_count += sum(
                1
                for period in (opening_hours.get("periods") or [])
                if isinstance(period, dict)
                and "open" in period
                and "close" not in period
            )
        schedule = normalize_google_regular_opening_hours(
            attraction_id=attraction_id,
            opening_hours=opening_hours,
        )
        status_counts[schedule.validation_status.value] += 1
        valid_count += int(schedule.validation_status.value == "valid")
        rejected_count += int(
            schedule.validation_status.value
            in {"malformed", "ambiguous", "unsupported", "conflicting"}
        )
        warning_counts.update(schedule.warnings)
        overnight_interval_count += sum(interval.overnight for interval in schedule.intervals)

        district_key = str(district_id) if district_id is not None else "unassigned"
        coverage = district_coverage.setdefault(
            district_key,
            {"active": 0, "structured": 0, "valid": 0},
        )
        coverage["active"] += 1
        coverage["structured"] += int(is_structured)
        coverage["valid"] += int(schedule.validation_status.value == "valid")

    return {
        "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "active_attractions": len(rows),
        "structured_schedule_count": structured_count,
        "successfully_normalized": valid_count,
        "rejected_schedule_count": rejected_count,
        "not_normalized_count": len(rows) - valid_count,
        "json_null_schedule_count": sum(opening_hours is None for _, _, opening_hours in rows),
        "missing_close_representation_count": missing_close_count,
        "overnight_interval_count": overnight_interval_count,
        "validation_status_counts": dict(status_counts),
        "warning_distribution": dict(warning_counts),
        "district_coverage": district_coverage,
    }


async def _main() -> None:
    async with AsyncSessionLocal() as db:
        report = await validate_pilot_schedules(db)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
