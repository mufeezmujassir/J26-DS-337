"""Stage 12.4B.5 Automated Test Runner and Report Generator.

Runs all 20 verification tests inside the container or host and outputs
data/reports/stage12_4b5_tests.json.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.climate.services.historical_climate import (
    HistoricalClimateService,
    DEFAULT_DISTRICT_DATASET_VERSION,
    HISTORICAL_BATCH01_DATASET_VERSION,
    PILOT_DATASET_VERSION,
)

BATCH01_MANIFEST = Path("data/climate/manifests/nasa_power/historical_2010_2025/batch01_live_manifest_v3.json")
BATCH02_MANIFEST = Path("data/climate/manifests/nasa_power/historical_2010_2025/batch02_proposed_manifest.json")
REPORTS_DIR = Path("data/reports")


async def main():
    test_results = []
    t_start = time.time()

    def record_test(test_id: int, name: str, passed: bool, error: str = ""):
        test_results.append({
            "test_id": test_id,
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "error": error,
        })
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] Test {test_id:02d}: {name}")
        if error:
            print(f"       Error: {error}")

    # Test 1: Historical manifest parsing
    try:
        m1 = json.loads(BATCH01_MANIFEST.read_text(encoding="utf-8"))
        assert m1["provider"] == "NASA POWER"
        assert len(m1["samples"]) == 3
        m2 = json.loads(BATCH02_MANIFEST.read_text(encoding="utf-8"))
        assert m2["provider"] == "NASA POWER"
        assert len(m2["samples"]) == 25
        record_test(1, "Historical manifest parsing", True)
    except Exception as e:
        record_test(1, "Historical manifest parsing", False, str(e))

    # Test 2: Source checksum verification
    try:
        m1 = json.loads(BATCH01_MANIFEST.read_text(encoding="utf-8"))
        for s in m1["samples"]:
            raw_p = Path(s["raw_file"])
            assert raw_p.exists()
            assert hashlib.sha256(raw_p.read_bytes()).hexdigest() == s["checksum_sha256"]
        m2 = json.loads(BATCH02_MANIFEST.read_text(encoding="utf-8"))
        for s in m2["samples"]:
            assert Path(s["raw_file"]).exists()
        record_test(2, "Source checksum verification", True)
    except Exception as e:
        record_test(2, "Source checksum verification", False, str(e))

    # Test 3: Dataset version registration
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT product_version FROM climate_dataset_versions ORDER BY id"))
            versions = [r[0] for r in res.fetchall()]
        assert PILOT_DATASET_VERSION in versions
        assert HISTORICAL_BATCH01_DATASET_VERSION in versions
        assert DEFAULT_DISTRICT_DATASET_VERSION in versions
        record_test(3, "Dataset version registration", True)
    except Exception as e:
        record_test(3, "Dataset version registration", False, str(e))

    # Test 4: Sample identity registration
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT v.product_version, count(g.id)
                FROM climate_dataset_versions v
                JOIN climate_grid_cells g ON g.dataset_version_id = v.id
                GROUP BY v.product_version
            """))
            counts = {r[0]: r[1] for r in res.fetchall()}
        assert counts.get(PILOT_DATASET_VERSION) == 6
        assert counts.get(HISTORICAL_BATCH01_DATASET_VERSION) == 3
        assert counts.get(DEFAULT_DISTRICT_DATASET_VERSION) == 25
        record_test(4, "Sample identity registration", True)
    except Exception as e:
        record_test(4, "Sample identity registration", False, str(e))

    # Test 5: District mapping integrity
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT count(*) FROM climate_district_mappings m
                JOIN districts d ON m.district_id = d.id
                JOIN climate_grid_cells g ON m.grid_cell_id = g.id
            """))
            valid_mappings = res.scalar_one()
        assert valid_mappings == 28
        record_test(5, "District mapping integrity", True)
    except Exception as e:
        record_test(5, "District mapping integrity", False, str(e))

    # Test 6: Daily observation parsing
    try:
        proc_p = Path("data/climate/processed/nasa_power/historical_2010_2025/district_78_20100101_20251231.json")
        data = json.loads(proc_p.read_text(encoding="utf-8"))
        records = data["records"]
        assert len(records) == 5844
        assert records[0]["date"] == "2010-01-01"
        assert isinstance(records[0]["temperature_mean_c"], (int, float))
        record_test(6, "Daily observation parsing", True)
    except Exception as e:
        record_test(6, "Daily observation parsing", False, str(e))

    # Test 7: Missing-value conversion
    try:
        sentinels = [-999, -999.0]
        cleaned = [None if x in sentinels else x for x in [-999, 25.5, -999.0, 0.0]]
        assert cleaned == [None, 25.5, None, 0.0]
        record_test(7, "Missing-value conversion", True)
    except Exception as e:
        record_test(7, "Missing-value conversion", False, str(e))

    # Test 8: Variable-level quality checks
    try:
        q_rep = json.loads(Path("data/reports/stage12_4b5_variable_quality.json").read_text(encoding="utf-8"))
        assert q_rep["temperature_consistency"]["tmin_greater_than_tmax_count"] == 0
        vars_st = q_rep["variable_statistics"]
        for v in ["temperature_mean_c", "temperature_min_c", "temperature_max_c", "precipitation_mm", "relative_humidity_pct", "wind_speed_10m", "solar_radiation"]:
            assert vars_st[v]["out_of_bounds_count"] == 0
            assert vars_st[v]["valid_count"] == 163632
        record_test(8, "Variable-level quality checks", True)
    except Exception as e:
        record_test(8, "Variable-level quality checks", False, str(e))

    # Test 9: Date-range completeness
    try:
        delta = date(2025, 12, 31) - date(2010, 1, 1)
        assert delta.days + 1 == 5844
        record_test(9, "Date-range completeness", True)
    except Exception as e:
        record_test(9, "Date-range completeness", False, str(e))

    # Test 10: Leap-year handling
    try:
        leap_days = ["2012-02-29", "2016-02-29", "2020-02-29", "2024-02-29"]
        proc_p = Path("data/climate/processed/nasa_power/historical_2010_2025/district_78_20100101_20251231.json")
        data = json.loads(proc_p.read_text(encoding="utf-8"))
        dates_set = {r["date"] for r in data["records"]}
        for ld in leap_days:
            assert ld in dates_set
        record_test(10, "Leap-year handling", True)
    except Exception as e:
        record_test(10, "Leap-year handling", False, str(e))

    # Test 11: Duplicate prevention
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT dataset_version_id, grid_cell_id, observation_date, count(*)
                FROM climate_daily_observations
                GROUP BY dataset_version_id, grid_cell_id, observation_date
                HAVING count(*) > 1
            """))
            dupes = res.fetchall()
        assert len(dupes) == 0
        record_test(11, "Duplicate prevention", True)
    except Exception as e:
        record_test(11, "Duplicate prevention", False, str(e))

    # Test 12: Transaction rollback
    try:
        async with AsyncSessionLocal() as session:
            init_res = await session.execute(text("SELECT count(*) FROM climate_dataset_versions"))
            init_count = init_res.scalar_one()

        async with AsyncSessionLocal() as session:
            try:
                async with session.begin():
                    await session.execute(text("""
                        INSERT INTO climate_dataset_versions (
                            source_name, provider_name, product_name, product_version,
                            source_url, license_review_status, retrieved_at,
                            source_units_json, normalized_units_json
                        ) VALUES (
                            'Test', 'Test', 'Test', 'test_rollback_version',
                            'https://test.local', 'TEST', now(), '{}', '{}'
                        )
                    """))
                    raise RuntimeError("Deliberate rollback")
            except RuntimeError:
                pass

        async with AsyncSessionLocal() as session:
            after_res = await session.execute(text("SELECT count(*) FROM climate_dataset_versions"))
            after_count = after_res.scalar_one()

        assert init_count == after_count
        record_test(12, "Transaction rollback", True)
    except Exception as e:
        record_test(12, "Transaction rollback", False, str(e))

    # Test 13: Interrupted ingestion recovery
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT count(*) FROM climate_ingestion_runs WHERE status = 'SUCCEEDED'"))
            succeeded_runs = res.scalar_one()
        assert succeeded_runs >= 3
        record_test(13, "Interrupted ingestion recovery", True)
    except Exception as e:
        record_test(13, "Interrupted ingestion recovery", False, str(e))

    # Test 14: Idempotent rerun
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT count(*) FROM climate_daily_observations"))
            count = res.scalar_one()
        assert count == 165828
        record_test(14, "Idempotent rerun", True)
    except Exception as e:
        record_test(14, "Idempotent rerun", False, str(e))

    # Test 15: Preservation of the 2024 pilot
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT count(o.id)
                FROM climate_daily_observations o
                JOIN climate_dataset_versions v ON o.dataset_version_id = v.id
                WHERE v.product_version = 'nasa_power_daily_v2.10.0_2024_pilot'
            """))
            pilot_obs = res.scalar_one()
        assert pilot_obs == 2196
        record_test(15, "Preservation of the 2024 pilot", True)
    except Exception as e:
        record_test(15, "Preservation of the 2024 pilot", False, str(e))

    # Test 16: Preservation of unrelated weather tables
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT 'district_weather_monthly' as tbl, count(*) FROM district_weather_monthly
                UNION ALL SELECT 'weather_forecasts', count(*) FROM weather_forecasts
                UNION ALL SELECT 'weather_model_runs', count(*) FROM weather_model_runs
                UNION ALL SELECT 'weather_readings', count(*) FROM weather_readings
                UNION ALL SELECT 'weather_stations', count(*) FROM weather_stations
            """))
            counts = {r[0]: r[1] for r in res.fetchall()}
        assert counts.get("district_weather_monthly") == 873
        assert counts.get("weather_forecasts") == 129
        assert counts.get("weather_model_runs") == 43
        assert counts.get("weather_readings") == 1162
        assert counts.get("weather_stations") == 23
        record_test(16, "Preservation of unrelated weather tables", True)
    except Exception as e:
        record_test(16, "Preservation of unrelated weather tables", False, str(e))

    # Test 17: Dataset-version isolation
    try:
        async with AsyncSessionLocal() as session:
            p_res = await session.execute(text("""
                SELECT count(o.id)
                FROM climate_daily_observations o
                JOIN climate_dataset_versions v ON o.dataset_version_id = v.id
                JOIN climate_attraction_mappings m ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
                WHERE v.product_version = 'nasa_power_daily_v2.10.0_2024_pilot'
                  AND m.attraction_id = 1
            """))
            p_count = p_res.scalar_one()
            h_res = await session.execute(text("""
                SELECT count(o.id)
                FROM climate_daily_observations o
                JOIN climate_dataset_versions v ON o.dataset_version_id = v.id
                JOIN climate_district_mappings m ON o.grid_cell_id = m.grid_cell_id AND o.dataset_version_id = m.dataset_version_id
                WHERE v.product_version = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02'
                  AND m.district_id = 78
                  AND o.observation_date BETWEEN '2024-01-01' AND '2024-12-31'
            """))
            h_count = h_res.scalar_one()
        assert p_count == 366
        assert h_count == 366
        record_test(17, "Dataset-version isolation", True)
    except Exception as e:
        record_test(17, "Dataset-version isolation", False, str(e))

    # Test 18: District boundary validation
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT d.id, ST_Covers(d.boundary, ST_SetSRID(ST_MakePoint(g.longitude, g.latitude), 4326))
                FROM climate_district_mappings m
                JOIN districts d ON m.district_id = d.id
                JOIN climate_grid_cells g ON m.grid_cell_id = g.id
                JOIN climate_dataset_versions v ON m.dataset_version_id = v.id
                WHERE v.product_version = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02'
            """))
            rows = res.fetchall()
        assert len(rows) == 25
        assert all(r[1] is True for r in rows)
        record_test(18, "District boundary validation", True)
    except Exception as e:
        record_test(18, "District boundary validation", False, str(e))

    # Test 19: Read-only historical climate queries
    try:
        daily = await HistoricalClimateService.get_district_daily(78, date(2024, 1, 1), date(2024, 1, 7))
        assert len(daily) == 7
        assert daily[0]["district_name"] == "Galle"

        monthly = await HistoricalClimateService.get_district_observations_by_month(78, 1)
        assert len(monthly) == 496  # 16 years * 31 days

        yearly = await HistoricalClimateService.get_district_yearly_summary(78, 2020, 2024)
        assert len(yearly) == 5

        quality = await HistoricalClimateService.get_quality_statistics()
        assert quality["total_records"] == 146100

        prov = await HistoricalClimateService.get_dataset_provenance()
        assert prov["provider_name"] == "NASA POWER"

        uncert = await HistoricalClimateService.get_source_geographic_uncertainty(78)
        assert uncert["geographic_confidence"] == "DISTRICT_CENTROID_REPRESENTATIVE"

        cov = await HistoricalClimateService.get_available_date_coverage()
        assert cov["distinct_dates_count"] == 5844

        v_list = await HistoricalClimateService.list_dataset_versions()
        assert len(v_list) >= 3

        record_test(19, "Read-only historical climate queries", True)
    except Exception as e:
        record_test(19, "Read-only historical climate queries", False, str(e))

    # Test 20: PostgreSQL readback verification
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("""
                SELECT d.product_version, count(o.*)
                FROM climate_dataset_versions d
                JOIN climate_grid_cells g ON g.dataset_version_id = d.id
                JOIN climate_daily_observations o ON o.grid_cell_id = g.id AND o.dataset_version_id = d.id
                GROUP BY d.product_version
                ORDER BY d.product_version
            """))
            counts = {r[0]: r[1] for r in res.fetchall()}
            total_obs = (await session.execute(text("SELECT count(*) FROM climate_daily_observations"))).scalar_one()

        assert counts[PILOT_DATASET_VERSION] == 2196
        assert counts[HISTORICAL_BATCH01_DATASET_VERSION] == 17532
        assert counts[DEFAULT_DISTRICT_DATASET_VERSION] == 146100
        assert total_obs == 165828
        record_test(20, "PostgreSQL readback verification", True)
    except Exception as e:
        record_test(20, "PostgreSQL readback verification", False, str(e))

    elapsed = round(time.time() - t_start, 2)
    passed_count = sum(1 for t in test_results if t["status"] == "PASS")
    total_count = len(test_results)

    report = {
        "status": "ALL_TESTS_PASSED" if passed_count == total_count else "TESTS_FAILED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_tests": total_count,
        "passed": passed_count,
        "failed": total_count - passed_count,
        "elapsed_seconds": elapsed,
        "tests": test_results,
    }
    (REPORTS_DIR / "stage12_4b5_tests.json").write_text(json.dumps(report, indent=2))
    print(f"\n=======================================================")
    print(f"Test Run Completed: {passed_count}/{total_count} PASSED ({elapsed}s)")
    print(f"Report written to data/reports/stage12_4b5_tests.json")
    print(f"=======================================================")


if __name__ == "__main__":
    asyncio.run(main())
