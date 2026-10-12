"""Audit historical monthly weather gaps without modifying observations.

The audit treats an absent database row differently from a row whose target
measurement is NULL.  Both prevent a complete-case backtest, but the
distinction is essential when deciding whether a source-data correction is
possible or whether only documented training-only imputation is appropriate.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.weather_model.persistence.database import get_weather_engine


TARGETS = ("rainfall_mm", "temperature_min_c", "temperature_max_c")
DEFAULT_START_MONTH = date(2021, 1, 1)
DEFAULT_END_MONTH = date(2025, 10, 1)
REPORT_DIR = Path("data/weather/reports/backtesting")
JSON_REPORT = REPORT_DIR / "missing_months_audit.json"
CSV_REPORT = REPORT_DIR / "missing_months_audit.csv"


def month_range(start: date, end: date) -> Iterable[date]:
    """Yield first-of-month dates inclusively."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, 1)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def load_weather_rows(engine: Engine, district_id: int | None = None) -> list[dict[str, Any]]:
    """Load districts and their monthly records, including districts with no rows."""
    district_filter = ""
    parameters: dict[str, int] = {}
    if district_id is not None:
        district_filter = "WHERE d.id = :district_id"
        parameters["district_id"] = district_id
    query = text(
        f"""
        SELECT
            d.id AS district_id,
            d.name AS district_name,
            w.observation_date,
            w.rainfall_mm,
            w.temperature_min_c,
            w.temperature_max_c
        FROM districts AS d
        LEFT JOIN district_weather_monthly AS w ON w.district_id = d.id
        {district_filter}
        ORDER BY d.id, w.observation_date
        """
    )
    with engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(query, parameters).mappings()
        ]


def _iso_month(value: date) -> str:
    return value.isoformat()


def audit_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    start_month: date,
    end_month: date,
) -> dict[str, Any]:
    """Build a serializable audit from database-like rows; performs no writes."""
    if start_month.day != 1 or end_month.day != 1 or start_month > end_month:
        raise ValueError("The audit period must be ordered first-of-month dates")

    expected_months = list(month_range(start_month, end_month))
    expected_set = set(expected_months)
    districts: dict[int, dict[str, Any]] = {}

    for row in rows:
        district_id = int(row["district_id"])
        district = districts.setdefault(
            district_id,
            {
                "district_id": district_id,
                "district_name": row.get("district_name"),
                "records": {},
            },
        )
        observation_date = row.get("observation_date")
        if observation_date is None:
            continue
        if observation_date.day != 1:
            raise ValueError(
                f"District {district_id} has non-month-start observation {observation_date}"
            )
        if observation_date in district["records"]:
            raise ValueError(
                f"District {district_id} has duplicate observation month {observation_date}"
            )
        district["records"][observation_date] = {
            target: row.get(target) for target in TARGETS
        }

    missing_rows: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    summary = {
        "districts": len(districts),
        "districts_without_monthly_records": 0,
        "series": 0,
        "complete_series": 0,
        "series_with_gaps": 0,
        "series_with_observations": 0,
        "series_with_observations_and_gaps": 0,
        "unsupported_no_observations": 0,
        "absent_monthly_records": 0,
        "missing_measurements": 0,
        "available_measurements": 0,
    }

    for district_id in sorted(districts):
        district = districts[district_id]
        if not district["records"]:
            summary["districts_without_monthly_records"] += 1
        target_audits: dict[str, Any] = {}
        for target in TARGETS:
            missing_months: list[dict[str, str]] = []
            available_months = 0
            for month in expected_months:
                record = district["records"].get(month)
                if record is None:
                    kind = "absent_monthly_record"
                    summary["absent_monthly_records"] += 1
                elif record[target] is None:
                    kind = "missing_measurement"
                    summary["missing_measurements"] += 1
                else:
                    available_months += 1
                    summary["available_measurements"] += 1
                    continue
                item = {"month": _iso_month(month), "kind": kind}
                missing_months.append(item)
                missing_rows.append(
                    {
                        "district_id": district_id,
                        "district_name": district["district_name"],
                        "target": target,
                        **item,
                    }
                )

            summary["series"] += 1
            if missing_months:
                summary["series_with_gaps"] += 1
            else:
                summary["complete_series"] += 1
            if available_months:
                summary["series_with_observations"] += 1
                if missing_months:
                    summary["series_with_observations_and_gaps"] += 1
            else:
                summary["unsupported_no_observations"] += 1
            target_audits[target] = {
                "expected_months": len(expected_months),
                "available_months": available_months,
                "coverage_ratio": round(available_months / len(expected_months), 6),
                "missing_months": missing_months,
            }
        series.append(
            {
                "district_id": district_id,
                "district_name": district["district_name"],
                "targets": target_audits,
                "out_of_window_record_months": sorted(
                    _iso_month(month)
                    for month in district["records"]
                    if month not in expected_set
                ),
            }
        )

    return {
        "stage": "9.8.7.6",
        "read_only": True,
        "expected_period": {
            "start_month": _iso_month(start_month),
            "end_month": _iso_month(end_month),
            "month_count": len(expected_months),
        },
        "summary": summary,
        "series": series,
        "missing_rows": missing_rows,
    }


def write_reports(audit: Mapping[str, Any], json_path: Path, csv_path: Path) -> None:
    """Write JSON evidence plus a spreadsheet-friendly missing-row export."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("district_id", "district_name", "target", "month", "kind"),
        )
        writer.writeheader()
        writer.writerows(audit["missing_rows"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-month", type=date.fromisoformat, default=DEFAULT_START_MONTH)
    parser.add_argument("--end-month", type=date.fromisoformat, default=DEFAULT_END_MONTH)
    parser.add_argument("--district-id", type=int)
    parser.add_argument("--json-output", type=Path, default=JSON_REPORT)
    parser.add_argument("--csv-output", type=Path, default=CSV_REPORT)
    arguments = parser.parse_args()

    engine = get_weather_engine()
    try:
        rows = load_weather_rows(engine, arguments.district_id)
    finally:
        engine.dispose()

    audit = audit_rows(
        rows,
        start_month=arguments.start_month,
        end_month=arguments.end_month,
    )
    write_reports(audit, arguments.json_output, arguments.csv_output)

    summary = audit["summary"]
    print("\n=== HISTORICAL MONTHLY GAP AUDIT ===")
    print("Expected period:", audit["expected_period"])
    print("Districts audited:", summary["districts"])
    print("Districts without any monthly records:", summary["districts_without_monthly_records"])
    print("Complete district-target series:", summary["complete_series"])
    print("Series with gaps:", summary["series_with_gaps"])
    print("Observed series with gaps:", summary["series_with_observations_and_gaps"])
    print("Unsupported series with no observations:", summary["unsupported_no_observations"])
    print("Absent monthly records:", summary["absent_monthly_records"])
    print("NULL target measurements:", summary["missing_measurements"])
    print("JSON report:", arguments.json_output)
    print("CSV report:", arguments.csv_output)


if __name__ == "__main__":
    main()
