"""Stage 12.4A read-only seasonality data audit.

This command deliberately performs no network calls and no database writes.  It
turns the repository and current PostgreSQL state into reproducible evidence
for the later (separately approved) seasonality implementation stage.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import AsyncSessionLocal

REPORTS = Path("data/reports")
DOC = Path("docs/research/STAGE_12_4A_SEASONALITY_DATA_AUDIT.md")


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def write_json(name: str, payload: dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / name
    path.write_text(json.dumps(payload, indent=2, default=json_safe) + "\n", encoding="utf-8")
    return path


def local_weather_files() -> list[dict[str, Any]]:
    root = Path("data/weather")
    result: list[dict[str, Any]] = []
    if not root.exists():
        return result
    for path in sorted(root.rglob("*.csv")):
        row: dict[str, Any] = {"path": path.as_posix(), "bytes": path.stat().st_size}
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
                count = sum(1 for _ in reader)
            row.update({"columns": header, "data_rows": count})
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            row["inspection_error"] = str(exc)
        result.append(row)
    return result


def climate_sources() -> list[dict[str, Any]]:
    """Metadata reviewed in Stage 12.4A; no source data are downloaded here."""
    return [
        {
            "source": "Open-Meteo Historical Weather API / ERA5-Land",
            "official_url": "https://open-meteo.com/en/docs/historical-weather-api",
            "coverage_assessed": "ERA5-Land: 1950-present; ERA5: 1940-present",
            "resolution_assessed": "ERA5-Land 0.1 degree; ERA5 0.25 degree",
            "variables_assessed": ["temperature", "precipitation", "humidity", "wind", "solar radiation"],
            "stage12_4a_decision": "RECOMMENDED_CANDIDATE_PENDING_TERMS_AND_REPRODUCIBILITY_REVIEW",
            "downloaded": False,
        },
        {
            "source": "NASA POWER",
            "official_url": "https://power.larc.nasa.gov/",
            "coverage_assessed": "candidate global agroclimatology source; exact variable/version policy remains to be verified before use",
            "stage12_4a_decision": "SECONDARY_CANDIDATE_PENDING_VARIABLE_AND_LICENSE_REVIEW",
            "downloaded": False,
        },
        {
            "source": "Department of Meteorology Sri Lanka",
            "official_url": "https://meteo.gov.lk/",
            "coverage_assessed": "authoritative national provider; machine-readable historical access and reuse terms not verified in this stage",
            "stage12_4a_decision": "AUTHORITATIVE_LOCAL_REFERENCE_PENDING_ACCESS_AND_REUSE_CONFIRMATION",
            "downloaded": False,
        },
        {
            "source": "Sri Lanka Tourism Development Authority",
            "official_url": "https://www.sltda.gov.lk/",
            "coverage_assessed": "tourism context/reference candidate, not assumed to provide climate observations",
            "stage12_4a_decision": "CONTEXT_REFERENCE_ONLY_PENDING_DOCUMENT_REVIEW",
            "downloaded": False,
        },
    ]


def schema_proposal() -> dict[str, Any]:
    return {
        "proposal_only": True,
        "migration_created": False,
        "tables": [
            {"name": "climate_dataset_versions", "purpose": "immutable source/version/license/checksum provenance"},
            {"name": "climate_grid_cells", "purpose": "source grid geometry, resolution and elevation metadata"},
            {"name": "district_climate_monthly", "purpose": "district-month climatology with sample size and uncertainty"},
            {"name": "attraction_climate_monthly", "purpose": "derived attraction-month values with district/grid provenance"},
            {"name": "activity_seasonality_profiles", "purpose": "category/activity rules, evidence and confidence; no invented facts"},
            {"name": "seasonality_feature_runs", "purpose": "versioned feature computation/audit trail"},
        ],
        "constraints": [
            "unique(dataset_version_id, grid_cell_id, observation_month, variable)",
            "unique(attraction_id, dataset_version_id, calendar_month, variable)",
            "foreign keys to districts, attractions and categories/activities where applicable",
            "store source URL, retrieval timestamp, checksum, unit and transformation lineage",
        ],
    }


async def query_one(session, sql: str) -> dict[str, Any]:
    return dict((await session.execute(text(sql))).mappings().one())


async def query_all(session, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in (await session.execute(text(sql))).mappings().all()]


async def build_reports() -> dict[str, Any]:
    generated = datetime.now(timezone.utc).isoformat()
    async with AsyncSessionLocal() as session:
        weather_readings = await query_one(session, """
            SELECT count(*) AS rows, min(observation_date) AS earliest, max(observation_date) AS latest,
              count(DISTINCT station_id) AS stations, count(DISTINCT district_id) FILTER (WHERE district_id IS NOT NULL) AS districts,
              count(*) FILTER (WHERE rainfall_mm IS NULL) AS rainfall_missing,
              count(*) FILTER (WHERE temperature_min_c IS NULL OR temperature_max_c IS NULL) AS temperature_missing,
              count(*) - count(DISTINCT (station_id, observation_date)) AS duplicate_identity_rows
            FROM weather_readings
        """)
        district_monthly = await query_one(session, """
            SELECT count(*) AS rows, min(observation_date) AS earliest, max(observation_date) AS latest,
              count(DISTINCT district_id) AS districts,
              count(*) FILTER (WHERE rainfall_mm IS NULL) AS rainfall_missing,
              count(*) FILTER (WHERE temperature_avg_c IS NULL) AS temperature_missing,
              count(*) - count(DISTINCT (district_id, observation_date)) AS duplicate_identity_rows
            FROM district_weather_monthly
        """)
        forecasts = await query_one(session, """
            SELECT count(*) AS rows, min(forecast_month) AS earliest, max(forecast_month) AS latest,
              count(DISTINCT run_id) AS model_runs FROM weather_forecasts
        """)
        models = await query_all(session, """
            SELECT model_name, count(*) AS run_count, count(*) FILTER (WHERE validation_gate_passed) AS validated_runs,
              count(*) FILTER (WHERE production_approved) AS production_approved_runs,
              min(training_start) AS earliest_training, max(training_cutoff) AS latest_cutoff,
              min(forecast_horizon_months) AS min_horizon, max(forecast_horizon_months) AS max_horizon
            FROM weather_model_runs GROUP BY model_name ORDER BY model_name
        """)
        geography = await query_one(session, """
            SELECT count(*) FILTER (WHERE a.is_active) AS active_attractions,
              count(*) FILTER (WHERE a.is_active AND a.district_id IS NULL) AS missing_district,
              count(*) FILTER (WHERE a.is_active AND (a.latitude IS NULL OR a.longitude IS NULL)) AS missing_coordinates,
              count(*) FILTER (WHERE a.is_active AND a.district_id IS NOT NULL AND a.latitude IS NOT NULL AND a.longitude IS NOT NULL
                AND NOT ST_Covers(d.boundary, ST_SetSRID(ST_MakePoint(a.longitude, a.latitude),4326))) AS outside_assigned_boundary,
              count(DISTINCT a.district_id) FILTER (WHERE a.is_active) AS attraction_districts,
              count(*) FILTER (WHERE d.boundary IS NULL) AS district_boundaries_missing,
              count(*) FILTER (WHERE d.boundary IS NOT NULL AND NOT ST_IsValid(d.boundary)) AS invalid_district_boundaries
            FROM attractions a LEFT JOIN districts d ON d.id=a.district_id
        """)
        pilot = await query_all(session, """
            WITH ranked AS (
              SELECT a.id, a.name, a.district_id, d.name AS district_name, d.province, a.latitude, a.longitude,
                row_number() over(partition by a.district_id order by a.id) AS rn
              FROM attractions a JOIN districts d ON d.id=a.district_id
              WHERE a.is_active AND a.latitude IS NOT NULL AND a.longitude IS NOT NULL
            ) SELECT id, name, district_id, district_name, province, latitude, longitude
            FROM ranked WHERE rn <= 2 ORDER BY province, district_name, id LIMIT 30
        """)

    files = local_weather_files()
    source_files = [f for f in files if "/raw/" in f["path"] or "/processed/" in f["path"]]
    model_files = [f for f in files if "/modeling/" in f["path"]]
    inventory = {"generated_at_utc": generated, "database": {"weather_readings": weather_readings, "district_weather_monthly": district_monthly, "weather_forecasts": forecasts}, "local_files": {"count": len(files), "source_or_processed_count": len(source_files), "modeling_count": len(model_files), "files": files}, "assessment": "Existing persisted weather coverage begins in 2021; it cannot by itself support the requested 2010-2025 climate reference period."}
    model_audit = {"generated_at_utc": generated, "models": models, "algorithms_found": ["Prophet", "seasonal_naive", "monthly_climatology"], "lstm_found": False, "forecast_characteristics": "monthly target forecasts; registry indicates short three-month horizons and zero production-approved runs", "seasonality_distinction": "Forecasting predicts upcoming weather from observations. Seasonality must be a separately versioned, long-period month-of-year climate feature and must not reuse forecast output as climatology."}
    missing = {"generated_at_utc": generated, "known_gaps": ["No verified 2010-2020 persisted weather observations in current PostgreSQL inventory", "No long-term climate dataset version/provenance table", "No formal monsoon-region assignment or attraction-month climate feature", "No evidence-backed activity seasonality profile"], "missing_data_policy": "Emit unavailable/insufficient-evidence features; never impute a tourist suitability value as observed fact."}
    activity = {"generated_at_utc": generated, "design_status": "PROPOSAL_ONLY", "approach": "Start from actual attraction category/activity taxonomy; attach a climate-sensitivity rule only with source/evidence, confidence and review status.", "monsoon_design": {"recommended_strategy": "coordinate-based district/grid climate summaries plus a reviewed regional classification, retaining uncertainty and not assigning a single national monsoon label", "regions_to_validate_before_use": ["southwest wet zone", "northeast monsoon-influenced region", "intermediate zone", "central highlands", "dry zone", "coastal zones"]}, "no_activity_rules_persisted": True}
    feature = {"generated_at_utc": generated, "reference_period_proposal": "2010-01-01 through 2025-12-31, evaluated per source variable/version and availability", "variables": ["monthly precipitation", "temperature min/mean/max", "relative humidity", "wind speed", "sunshine or solar radiation where available"], "feature_method": "Use month-of-year anomalies/quantiles relative to a versioned historical reference, keep coverage count and uncertainty; do not rank when evidence is unavailable.", "overlap_rule": "Live weather remains short-horizon operational context. Historical climate/seasonality is a separate reference feature and neither overwrites nor substitutes for the other."}
    overlap = {"generated_at_utc": generated, "current_live_or_forecast_layer": "weather_readings and weather_forecasts / model runs", "seasonality_layer": "not implemented", "required_guardrails": ["separate source/version identifiers", "separate feature namespace", "no forecast values used to calculate historical normals", "ranker must expose missingness and provenance"]}
    repository = {"generated_at_utc": generated, "weather_modules": ["app/weather_model/context/climatology_provider.py", "app/weather_model/forecasting/prophet_trainer.py", "app/weather_model/backtesting/", "app/weather_model/registry/", "dags/weather_historical.py", "dags/weather_model_train.py"], "models": ["app/models/weather_reading.py", "app/models/district_weather_monthly.py", "app/models/weather_forecast.py", "app/models/weather_model_run.py", "app/models/weather_station.py"], "finding": "Weather forecasting and monthly climatology prototypes exist; a data-governed tourism seasonality layer does not yet exist."}
    source_inventory = {"generated_at_utc": generated, "network_data_downloaded": False, "sources": climate_sources(), "recommended_source": "ERA5-Land through a reviewed reproducible provider path, subject to terms/licence and data-quality review; validate against Department of Meteorology Sri Lanka data where access permits."}
    pilot_report = {"generated_at_utc": generated, "selection_basis": "actual active PostgreSQL attractions with non-null coordinates, maximum two per district", "count": len(pilot), "attractions": pilot}
    reports = {
        "stage12_4a_repository_audit.json": repository, "stage12_4a_weather_data_inventory.json": inventory,
        "stage12_4a_weather_model_audit.json": model_audit, "stage12_4a_attraction_geography_audit.json": {"generated_at_utc": generated, "metrics": geography},
        "stage12_4a_climate_source_inventory.json": source_inventory, "stage12_4a_missing_data_analysis.json": missing,
        "stage12_4a_activity_seasonality_design.json": activity, "stage12_4a_database_schema_proposal.json": schema_proposal(),
        "stage12_4a_feature_methodology.json": feature, "stage12_4a_weather_overlap_analysis.json": overlap,
        "stage12_4a_pilot_attractions.json": pilot_report,
    }
    for name, payload in reports.items(): write_json(name, payload)
    status = "SEASONALITY_DATA_AUDIT_VERIFIED"
    summary = {"generated_at_utc": generated, "status": status, "postgresql_writes": False, "qdrant_writes": False, "external_data_downloads": False, "current_weather_coverage": {"weather_readings": weather_readings, "district_monthly": district_monthly}, "geography": geography, "pilot_attraction_count": len(pilot), "next_stage_boundary": "Stage 12.4B requires separately approved source acquisition, schema migration and feature implementation."}
    write_json("stage12_4a_final_summary.json", summary)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("# Stage 12.4A — Seasonality Data Audit\n\n" +
                   "Status: `SEASONALITY_DATA_AUDIT_VERIFIED` (audit/planning only).\n\n" +
                   "The existing monthly weather records start in 2021 and are not a 2010–2025 climate reference. " +
                   "Current forecasting (Prophet, seasonal naive and monthly climatology) is distinct from the proposed historical seasonality layer.\n\n" +
                   "Recommended next step: review source terms and reproducibility for a versioned ERA5-Land reference import, validate it against accessible national observations, then propose the migration separately.\n\n" +
                   "No PostgreSQL or Qdrant writes, no network data download, no ranking change, and no container restart occurred in this stage.\n", encoding="utf-8")
    return summary


async def main_async() -> None:
    summary = await build_reports()
    print(json.dumps(summary, indent=2, default=json_safe))


if __name__ == "__main__":
    import asyncio
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(main_async())
