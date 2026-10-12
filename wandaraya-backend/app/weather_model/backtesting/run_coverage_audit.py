"""Report weather-observation coverage per district without training any model."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.weather_model.persistence.database import get_weather_engine


MINIMUM_CANDIDATE_OBSERVATIONS = 39
OUTPUT_PATH = Path("data/weather/reports/backtesting/district_coverage_audit.json")


def load_district_coverage(engine: Engine) -> list[dict[str, Any]]:
    """Return counts including districts that currently have no weather rows."""
    query = text(
        """
        SELECT
            d.id AS district_id,
            d.name AS district_name,
            COUNT(w.id) AS total_months,
            COUNT(w.rainfall_mm) AS rainfall_mm,
            COUNT(w.temperature_min_c) AS temperature_min_c,
            COUNT(w.temperature_max_c) AS temperature_max_c,
            MIN(w.observation_date) AS first_month,
            MAX(w.observation_date) AS last_month
        FROM districts AS d
        LEFT JOIN district_weather_monthly AS w ON w.district_id = d.id
        GROUP BY d.id, d.name
        ORDER BY d.id
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
    results = []
    for row in rows:
        targets = {
            "rainfall_mm": int(row["rainfall_mm"]),
            "temperature_min_c": int(row["temperature_min_c"]),
            "temperature_max_c": int(row["temperature_max_c"]),
        }
        results.append(
            {
                "district_id": int(row["district_id"]),
                "district_name": row["district_name"],
                "total_months": int(row["total_months"]),
                "targets": targets,
                "candidate_targets": [
                    target
                    for target, count in targets.items()
                    if count >= MINIMUM_CANDIDATE_OBSERVATIONS
                ],
                "first_month": str(row["first_month"]) if row["first_month"] else None,
                "last_month": str(row["last_month"]) if row["last_month"] else None,
            }
        )
    return results


def main() -> None:
    engine = get_weather_engine()
    try:
        results = load_district_coverage(engine)
    finally:
        engine.dispose()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\nDISTRICT WEATHER COVERAGE")
    print("-" * 75)
    for item in results:
        print(
            f"{item['district_id']:>3} "
            f"{item['district_name']:<22} "
            f"Rain={item['targets']['rainfall_mm']:>3} "
            f"Tmin={item['targets']['temperature_min_c']:>3} "
            f"Tmax={item['targets']['temperature_max_c']:>3}"
        )
    print("\nDistricts:", len(results))
    print(
        "Candidate district-target pairs:",
        sum(len(item["candidate_targets"]) for item in results),
    )
    print("Report:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
