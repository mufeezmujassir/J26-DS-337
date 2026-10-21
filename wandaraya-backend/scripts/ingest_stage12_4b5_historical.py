"""WANDARAYA Stage 12.4B.5 Historical Climate Ingestion CLI.

Persists historical climate observations (2010-2025) for:
- Batch 01: 3 attraction-coordinate samples (17,532 records)
- Batch 02: 25 district-representative samples (146,100 records)
Total historical: 163,632 records.
Preserves existing 2024 pilot (2,196 records).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text
from app.database import AsyncSessionLocal

BATCH01_MANIFEST = Path("data/climate/manifests/nasa_power/historical_2010_2025/batch01_live_manifest_v3.json")
BATCH02_MANIFEST = Path("data/climate/manifests/nasa_power/historical_2010_2025/batch02_proposed_manifest.json")
REPORTS_DIR = Path("data/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

BATCH_CHUNK_SIZE = 2000

NORMALIZED_UNITS = {
    "precipitation_mm": "mm/day",
    "temperature_mean_c": "C",
    "temperature_min_c": "C",
    "temperature_max_c": "C",
    "relative_humidity_pct": "%",
    "wind_speed_10m": "m/s",
    "solar_radiation": "MJ/m^2/day",
}


def compute_record_hash(row: Dict[str, Any]) -> str:
    serialized = json.dumps(row, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def ingest_batch01(dry_run: bool = False) -> Dict[str, Any]:
    manifest = json.loads(BATCH01_MANIFEST.read_text(encoding="utf-8"))
    dataset_version = "nasa_power_daily_v2.10.0_historical_2010_2025_batch01"
    start_time = datetime.now(timezone.utc)
    t0 = time.time()

    samples = manifest["samples"]
    total_records = sum(s["accepted_dates"] for s in samples)

    if dry_run:
        return {
            "batch": "batch01",
            "status": "DRY_RUN_VALIDATED",
            "dataset_version": dataset_version,
            "samples_count": len(samples),
            "records_to_insert": total_records,
            "dry_run": True,
        }

    inserted_cells = 0
    inserted_attraction_mappings = 0
    inserted_district_mappings = 0
    inserted_observations = 0

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Dataset Version registration
            d_res = await session.execute(
                text("""
                    INSERT INTO climate_dataset_versions (
                        source_name, provider_name, product_name, product_version,
                        source_url, license_review_status, attribution_text,
                        reference_start, reference_end, retrieved_at,
                        request_manifest_hash, dataset_checksum,
                        source_units_json, normalized_units_json
                    ) VALUES (
                        'NASA POWER Daily API', 'NASA POWER', 'source-native daily meteorological data', :version,
                        'https://power.larc.nasa.gov/api/temporal/daily/point', 'DOCUMENTED_REVIEW_REQUIRED', 'NASA POWER',
                        DATE '2010-01-01', DATE '2025-12-31', :now,
                        :manifest_hash, :dataset_checksum,
                        :source_units, :normalized_units
                    )
                    ON CONFLICT (provider_name, product_name, product_version)
                    DO UPDATE SET product_version = EXCLUDED.product_version
                    RETURNING id
                """),
                {
                    "version": dataset_version,
                    "now": start_time,
                    "manifest_hash": manifest.get("manifest_sha256"),
                    "dataset_checksum": manifest.get("manifest_sha256"),
                    "source_units": json.dumps(samples[0]["metadata"]["units"]),
                    "normalized_units": json.dumps(NORMALIZED_UNITS),
                },
            )
            dataset_id = d_res.scalar_one()

            # District mapping reference for Batch 01
            attr_to_district = {1: 78, 16: 74, 24: 92}

            # 2. Ingest samples
            for s in samples:
                attr_id = s["attraction_id"]
                grid_key = f"provider_coordinate:{attr_id}"
                proc_p = Path(s["raw_file"].replace("raw/nasa_power", "processed/nasa_power"))
                proc_data = json.loads(proc_p.read_text(encoding="utf-8"))
                lat = proc_data["location"]["latitude"]
                lon = proc_data["location"]["longitude"]

                cell_res = await session.execute(
                    text("""
                        INSERT INTO climate_grid_cells (
                            dataset_version_id, source_grid_identifier, latitude, longitude,
                            geometry, spatial_resolution, metadata_json
                        ) VALUES (
                            :dataset_id, :grid_key, :lat, :lon,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                            'source_native_resolution_unverified', :metadata
                        )
                        ON CONFLICT (dataset_version_id, source_grid_identifier)
                        DO UPDATE SET source_grid_identifier = EXCLUDED.source_grid_identifier
                        RETURNING id
                    """),
                    {
                        "dataset_id": dataset_id,
                        "grid_key": grid_key,
                        "lat": lat,
                        "lon": lon,
                        "metadata": json.dumps({
                            "identity": "provider_coordinate_identified_not_source_grid_identified",
                            "sample_id": s["sample_id"],
                            "attraction_id": attr_id,
                            "name": s["name"],
                            "selection_method": s["selection_method"],
                            "raw_checksum_sha256": s["checksum_sha256"],
                        }),
                    },
                )
                grid_id = cell_res.scalar_one()
                inserted_cells += 1

                # Attraction mapping
                map_res = await session.execute(
                    text("""
                        INSERT INTO climate_attraction_mappings (
                            attraction_id, dataset_version_id, grid_cell_id,
                            mapping_method, distance_km, geographic_confidence, created_at
                        ) VALUES (
                            :attraction_id, :dataset_id, :grid_id,
                            'REQUEST_POINT_SAMPLED', 0.0, 'EXPERIMENTAL_COARSE_GRID', :now
                        )
                        ON CONFLICT (attraction_id, dataset_version_id) DO NOTHING
                    """),
                    {
                        "attraction_id": attr_id,
                        "dataset_id": dataset_id,
                        "grid_id": grid_id,
                        "now": start_time,
                    },
                )
                inserted_attraction_mappings += (map_res.rowcount if map_res.rowcount > 0 else 0)

                # District mapping
                did = attr_to_district.get(attr_id)
                if did:
                    dmap_res = await session.execute(
                        text("""
                            INSERT INTO climate_district_mappings (
                                district_id, dataset_version_id, grid_cell_id,
                                mapping_method, distance_km, geographic_confidence, created_at
                            ) VALUES (
                                :district_id, :dataset_id, :grid_id,
                                'ATTRACTION_COORDINATE_DISTRICT_ASSOC', 0.0, 'ATTRACTION_SAMPLE_POINT', :now
                            )
                            ON CONFLICT (district_id, dataset_version_id) DO NOTHING
                        """),
                        {
                            "district_id": did,
                            "dataset_id": dataset_id,
                            "grid_id": grid_id,
                            "now": start_time,
                        },
                    )
                    inserted_district_mappings += (dmap_res.rowcount if dmap_res.rowcount > 0 else 0)

                # 3. Daily observations in chunks
                records = proc_data["records"]
                rows = []
                for r in records:
                    rec_hash = compute_record_hash(r)
                    rows.append({
                        "dataset_id": dataset_id,
                        "grid_id": grid_id,
                        "date": r["date"],
                        "rain": r["precipitation_mm"],
                        "mean": r["temperature_mean_c"],
                        "min": r["temperature_min_c"],
                        "max": r["temperature_max_c"],
                        "rh": r["relative_humidity_pct"],
                        "wind": r["wind_speed_10m"],
                        "solar": r["solar_radiation"],
                        "hash": rec_hash,
                        "now": start_time,
                    })

                for i in range(0, len(rows), BATCH_CHUNK_SIZE):
                    chunk = rows[i:i + BATCH_CHUNK_SIZE]
                    obs_res = await session.execute(
                        text("""
                            INSERT INTO climate_daily_observations (
                                dataset_version_id, grid_cell_id, observation_date,
                                precipitation_mm, temperature_mean_c, temperature_min_c, temperature_max_c,
                                relative_humidity_pct, wind_speed, wind_speed_unit,
                                solar_radiation, solar_radiation_unit,
                                quality_status, source_record_hash, created_at
                            ) VALUES (
                                :dataset_id, :grid_id, :date,
                                :rain, :mean, :min, :max,
                                :rh, :wind, 'm/s',
                                :solar, 'MJ/m^2/day',
                                'VALIDATED', :hash, :now
                            )
                            ON CONFLICT (dataset_version_id, grid_cell_id, observation_date) DO NOTHING
                        """),
                        chunk,
                    )
                    inserted_observations += (obs_res.rowcount if obs_res.rowcount > 0 else 0)

            # 4. Ingestion run audit
            end_time = datetime.now(timezone.utc)
            await session.execute(
                text("""
                    INSERT INTO climate_ingestion_runs (
                        dataset_version_id, started_at, completed_at, status,
                        request_count, records_received, records_accepted, records_rejected,
                        manifest_path
                    ) VALUES (
                        :dataset_id, :started_at, :completed_at, 'SUCCEEDED',
                        :req_count, :received, :accepted, 0, :manifest_path
                    )
                """),
                {
                    "dataset_id": dataset_id,
                    "started_at": start_time,
                    "completed_at": end_time,
                    "req_count": len(samples),
                    "received": total_records,
                    "accepted": total_records,
                    "manifest_path": str(BATCH01_MANIFEST),
                },
            )

    elapsed = round(time.time() - t0, 2)
    return {
        "batch": "batch01",
        "status": "INGESTION_SUCCEEDED",
        "dataset_version": dataset_version,
        "dataset_version_id": dataset_id,
        "grid_cells_touched": inserted_cells,
        "attraction_mappings_inserted": inserted_attraction_mappings,
        "district_mappings_inserted": inserted_district_mappings,
        "observations_inserted": inserted_observations,
        "expected_observations": total_records,
        "elapsed_seconds": elapsed,
    }


async def ingest_batch02(dry_run: bool = False) -> Dict[str, Any]:
    manifest = json.loads(BATCH02_MANIFEST.read_text(encoding="utf-8"))
    dataset_version = "nasa_power_daily_v2.10.0_historical_2010_2025_batch02"
    start_time = datetime.now(timezone.utc)
    t0 = time.time()

    samples = manifest["samples"]
    total_records = sum(s["expected_records"] for s in samples)

    if dry_run:
        return {
            "batch": "batch02",
            "status": "DRY_RUN_VALIDATED",
            "dataset_version": dataset_version,
            "samples_count": len(samples),
            "records_to_insert": total_records,
            "dry_run": True,
        }

    inserted_cells = 0
    inserted_district_mappings = 0
    inserted_observations = 0

    # Get sample metadata units from sample 0 processed file
    first_proc = json.loads(Path(samples[0]["processed_file"]).read_text(encoding="utf-8"))
    source_units = first_proc["metadata"]["units"]
    manifest_bytes = BATCH02_MANIFEST.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Dataset Version registration
            d_res = await session.execute(
                text("""
                    INSERT INTO climate_dataset_versions (
                        source_name, provider_name, product_name, product_version,
                        source_url, license_review_status, attribution_text,
                        reference_start, reference_end, retrieved_at,
                        request_manifest_hash, dataset_checksum,
                        source_units_json, normalized_units_json
                    ) VALUES (
                        'NASA POWER Daily API', 'NASA POWER', 'source-native daily meteorological data', :version,
                        'https://power.larc.nasa.gov/api/temporal/daily/point', 'DOCUMENTED_REVIEW_REQUIRED', 'NASA POWER',
                        DATE '2010-01-01', DATE '2025-12-31', :now,
                        :manifest_hash, :dataset_checksum,
                        :source_units, :normalized_units
                    )
                    ON CONFLICT (provider_name, product_name, product_version)
                    DO UPDATE SET product_version = EXCLUDED.product_version
                    RETURNING id
                """),
                {
                    "version": dataset_version,
                    "now": start_time,
                    "manifest_hash": manifest_sha,
                    "dataset_checksum": manifest_sha,
                    "source_units": json.dumps(source_units),
                    "normalized_units": json.dumps(NORMALIZED_UNITS),
                },
            )
            dataset_id = d_res.scalar_one()

            # 2. Ingest samples
            for s in samples:
                did = s["district_id"]
                grid_key = f"district_representative:{did}"
                proc_p = Path(s["processed_file"])
                proc_data = json.loads(proc_p.read_text(encoding="utf-8"))
                lat = s["latitude"]
                lon = s["longitude"]

                raw_bytes = Path(s["raw_file"]).read_bytes()
                raw_sha = hashlib.sha256(raw_bytes).hexdigest()

                cell_res = await session.execute(
                    text("""
                        INSERT INTO climate_grid_cells (
                            dataset_version_id, source_grid_identifier, latitude, longitude,
                            geometry, spatial_resolution, metadata_json
                        ) VALUES (
                            :dataset_id, :grid_key, :lat, :lon,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                            'source_native_resolution_unverified', :metadata
                        )
                        ON CONFLICT (dataset_version_id, source_grid_identifier)
                        DO UPDATE SET source_grid_identifier = EXCLUDED.source_grid_identifier
                        RETURNING id
                    """),
                    {
                        "dataset_id": dataset_id,
                        "grid_key": grid_key,
                        "lat": lat,
                        "lon": lon,
                        "metadata": json.dumps({
                            "identity": "district_representative_coordinate_not_source_grid_identified",
                            "sample_id": s["sample_id"],
                            "district_id": did,
                            "district_name": s["district_name"],
                            "province": s["province"],
                            "selection_method": s["selection_method"],
                            "spatial_uncertainty": s["spatial_uncertainty"],
                            "raw_checksum_sha256": raw_sha,
                        }),
                    },
                )
                grid_id = cell_res.scalar_one()
                inserted_cells += 1

                # District mapping
                dmap_res = await session.execute(
                    text("""
                        INSERT INTO climate_district_mappings (
                            district_id, dataset_version_id, grid_cell_id,
                            mapping_method, distance_km, geographic_confidence, created_at
                        ) VALUES (
                            :district_id, :dataset_id, :grid_id,
                            'DISTRICT_REPRESENTATIVE_COORDINATE', 0.0, 'DISTRICT_CENTROID_REPRESENTATIVE', :now
                        )
                        ON CONFLICT (district_id, dataset_version_id) DO NOTHING
                    """),
                    {
                        "district_id": did,
                        "dataset_id": dataset_id,
                        "grid_id": grid_id,
                        "now": start_time,
                    },
                )
                inserted_district_mappings += (dmap_res.rowcount if dmap_res.rowcount > 0 else 0)

                # 3. Daily observations in chunks
                records = proc_data["records"]
                rows = []
                for r in records:
                    rec_hash = compute_record_hash(r)
                    rows.append({
                        "dataset_id": dataset_id,
                        "grid_id": grid_id,
                        "date": r["date"],
                        "rain": r["precipitation_mm"],
                        "mean": r["temperature_mean_c"],
                        "min": r["temperature_min_c"],
                        "max": r["temperature_max_c"],
                        "rh": r["relative_humidity_pct"],
                        "wind": r["wind_speed_10m"],
                        "solar": r["solar_radiation"],
                        "hash": rec_hash,
                        "now": start_time,
                    })

                for i in range(0, len(rows), BATCH_CHUNK_SIZE):
                    chunk = rows[i:i + BATCH_CHUNK_SIZE]
                    obs_res = await session.execute(
                        text("""
                            INSERT INTO climate_daily_observations (
                                dataset_version_id, grid_cell_id, observation_date,
                                precipitation_mm, temperature_mean_c, temperature_min_c, temperature_max_c,
                                relative_humidity_pct, wind_speed, wind_speed_unit,
                                solar_radiation, solar_radiation_unit,
                                quality_status, source_record_hash, created_at
                            ) VALUES (
                                :dataset_id, :grid_id, :date,
                                :rain, :mean, :min, :max,
                                :rh, :wind, 'm/s',
                                :solar, 'MJ/m^2/day',
                                'VALIDATED', :hash, :now
                            )
                            ON CONFLICT (dataset_version_id, grid_cell_id, observation_date) DO NOTHING
                        """),
                        chunk,
                    )
                    inserted_observations += (obs_res.rowcount if obs_res.rowcount > 0 else 0)

            # 4. Ingestion run audit
            end_time = datetime.now(timezone.utc)
            await session.execute(
                text("""
                    INSERT INTO climate_ingestion_runs (
                        dataset_version_id, started_at, completed_at, status,
                        request_count, records_received, records_accepted, records_rejected,
                        manifest_path
                    ) VALUES (
                        :dataset_id, :started_at, :completed_at, 'SUCCEEDED',
                        :req_count, :received, :accepted, 0, :manifest_path
                    )
                """),
                {
                    "dataset_id": dataset_id,
                    "started_at": start_time,
                    "completed_at": end_time,
                    "req_count": len(samples),
                    "received": total_records,
                    "accepted": total_records,
                    "manifest_path": str(BATCH02_MANIFEST),
                },
            )

    elapsed = round(time.time() - t0, 2)
    return {
        "batch": "batch02",
        "status": "INGESTION_SUCCEEDED",
        "dataset_version": dataset_version,
        "dataset_version_id": dataset_id,
        "grid_cells_touched": inserted_cells,
        "district_mappings_inserted": inserted_district_mappings,
        "observations_inserted": inserted_observations,
        "expected_observations": total_records,
        "elapsed_seconds": elapsed,
    }


async def verify_post_ingestion() -> Dict[str, Any]:
    async with AsyncSessionLocal() as session:
        # Table counts
        tbl_res = await session.execute(text("""
            SELECT 'climate_dataset_versions' as tbl, count(*) FROM climate_dataset_versions
            UNION ALL SELECT 'climate_grid_cells', count(*) FROM climate_grid_cells
            UNION ALL SELECT 'climate_daily_observations', count(*) FROM climate_daily_observations
            UNION ALL SELECT 'climate_attraction_mappings', count(*) FROM climate_attraction_mappings
            UNION ALL SELECT 'climate_district_mappings', count(*) FROM climate_district_mappings
            UNION ALL SELECT 'climate_ingestion_runs', count(*) FROM climate_ingestion_runs
        """))
        counts = {r[0]: r[1] for r in tbl_res.fetchall()}

        # Counts by dataset version
        ver_res = await session.execute(text("""
            SELECT d.product_version, count(o.*) as obs_count, count(DISTINCT o.grid_cell_id) as cell_count,
                   min(o.observation_date) as min_date, max(o.observation_date) as max_date
            FROM climate_dataset_versions d
            JOIN climate_grid_cells g ON g.dataset_version_id = d.id
            LEFT JOIN climate_daily_observations o ON o.grid_cell_id = g.id AND o.dataset_version_id = d.id
            GROUP BY d.product_version
            ORDER BY d.product_version
        """))
        versions = [
            {
                "version": r[0],
                "observation_count": r[1],
                "cell_count": r[2],
                "min_date": str(r[3]),
                "max_date": str(r[4]),
            }
            for r in ver_res.fetchall()
        ]

        # Orphan observations check
        orphan_res = await session.execute(text("""
            SELECT count(*) FROM climate_daily_observations o
            LEFT JOIN climate_grid_cells g ON o.grid_cell_id = g.id
            WHERE g.id IS NULL
        """))
        orphan_count = orphan_res.scalar_one()

        # Unrelated weather table check (preservation)
        weather_res = await session.execute(text("""
            SELECT 'district_weather_monthly' as tbl, count(*) FROM district_weather_monthly
            UNION ALL SELECT 'weather_forecasts', count(*) FROM weather_forecasts
            UNION ALL SELECT 'weather_model_runs', count(*) FROM weather_model_runs
            UNION ALL SELECT 'weather_readings', count(*) FROM weather_readings
            UNION ALL SELECT 'weather_stations', count(*) FROM weather_stations
        """))
        weather_counts = {r[0]: r[1] for r in weather_res.fetchall()}

    verification = {
        "status": "DATABASE_READBACK_VERIFIED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "table_counts": counts,
        "dataset_version_breakdown": versions,
        "orphan_observations": orphan_count,
        "weather_tables_preserved": weather_counts,
        "integrity_checks": {
            "pilot_preserved_2196": any(v["version"] == "nasa_power_daily_v2.10.0_2024_pilot" and v["observation_count"] == 2196 for v in versions),
            "batch01_persisted_17532": any(v["version"] == "nasa_power_daily_v2.10.0_historical_2010_2025_batch01" and v["observation_count"] == 17532 for v in versions),
            "batch02_persisted_146100": any(v["version"] == "nasa_power_daily_v2.10.0_historical_2010_2025_batch02" and v["observation_count"] == 146100 for v in versions),
            "total_observations_165828": counts.get("climate_daily_observations") == 165828,
            "zero_orphan_observations": orphan_count == 0,
            "district_mappings_count_28": counts.get("climate_district_mappings") == 28,  # 25 from batch02 + 3 from batch01
        }
    }
    (REPORTS_DIR / "stage12_4b5_database_readback.json").write_text(json.dumps(verification, indent=2))
    return verification


async def main():
    parser = argparse.ArgumentParser(description="Ingest NASA POWER historical climate datasets")
    parser.add_argument("--batch", choices=["batch01", "batch02", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results = []
    print(f"Starting Ingestion Process (batch={args.batch}, dry_run={args.dry_run})...")

    if args.batch in ("batch01", "all"):
        print("Processing Batch 01 (Attraction Samples: 3 x 5,844)...")
        r1 = await ingest_batch01(dry_run=args.dry_run)
        results.append(r1)
        print("  Batch 01 result:", r1.get("status"), f"Obs: {r1.get('observations_inserted', 0)}")

    if args.batch in ("batch02", "all"):
        print("Processing Batch 02 (District Samples: 25 x 5,844)...")
        r2 = await ingest_batch02(dry_run=args.dry_run)
        results.append(r2)
        print("  Batch 02 result:", r2.get("status"), f"Obs: {r2.get('observations_inserted', 0)}")

    if not args.dry_run:
        print("Running Post-Ingestion Database Readback Verification...")
        readback = await verify_post_ingestion()
        print("  Total climate observations:", readback["table_counts"].get("climate_daily_observations"))
        print("  All integrity checks passed:", all(readback["integrity_checks"].values()))

    summary = {
        "status": "INGESTION_COMPLETED" if not args.dry_run else "DRY_RUN_COMPLETED",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "batch_results": results,
    }
    (REPORTS_DIR / "stage12_4b5_ingestion_summary.json").write_text(json.dumps(summary, indent=2))
    print("Ingestion summary written to data/reports/stage12_4b5_ingestion_summary.json")


if __name__ == "__main__":
    asyncio.run(main())
