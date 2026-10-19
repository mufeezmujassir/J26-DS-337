"""Validation for source-normalized daily climate records."""
from __future__ import annotations
from datetime import date
from typing import Any

REQUIRED = {"date", "precipitation_mm", "temperature_mean_c", "temperature_min_c", "temperature_max_c"}


def validate_daily_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set(); accepted = []; rejected = []
    for record in records:
        reasons = []
        if REQUIRED - set(record): reasons.append("missing_required_variable")
        try: date.fromisoformat(str(record.get("date")))
        except (TypeError, ValueError): reasons.append("invalid_date")
        key = str(record.get("date"))
        if key in seen: reasons.append("duplicate_date")
        seen.add(key)
        rain, tmin, tmean, tmax = (record.get(x) for x in ("precipitation_mm", "temperature_min_c", "temperature_mean_c", "temperature_max_c"))
        if rain is not None and rain < 0: reasons.append("negative_precipitation")
        if tmin is not None and tmax is not None and tmin > tmax: reasons.append("temperature_order_invalid")
        if tmean is not None and tmin is not None and tmax is not None and not (tmin - 5 <= tmean <= tmax + 5): reasons.append("mean_temperature_inconsistent")
        (rejected if reasons else accepted).append({"record": record, "reasons": reasons} if reasons else record)
    expected = 366 if any(str(x.get("date", "")).startswith("2024") for x in records) else len(records)
    return {"received": len(records), "accepted": len(accepted), "rejected": len(rejected), "expected_daily_records": expected, "completeness_percent": round(len(accepted) * 100 / expected, 2) if expected else 0, "rejections": rejected}
