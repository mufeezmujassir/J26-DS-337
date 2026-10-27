"""Run actual Alembic chain in a new database on the isolated test server only."""
import json
import hashlib
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from app.climate.historical_executor import checkpoints, import_sample
from app.models.climate import ClimateDatasetVersion, ClimateGridCell, ClimateDailyObservation
from scripts.audit_stage12_4b5_historical import EXPECTED
from scripts.test_stage12_4b5_postgres_executor import load_verified, VERSIONS

CONTAINER = "wandaraya-climate-executor-integration-test"
DATABASE = "climate_safety_4b9_test"
USER = "climate_executor_test"
REPORT = Path("data/reports/stage12_4b9_integration_tests.json")


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout.strip()


def main():
    info = json.loads(docker("inspect", CONTAINER))[0]
    ports = info["NetworkSettings"]["Ports"]["5432/tcp"]
    mounts = info["Mounts"]
    if info["Config"]["Image"] != "postgis/postgis:17-3.5" or len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1" or any(m.get("Source", "").lower().endswith("postgres-data") for m in mounts):
        raise RuntimeError("unsafe isolated container configuration")
    env = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    if env.get("POSTGRES_USER") != USER or env.get("POSTGRES_DB") != "climate_executor_isolated_test":
        raise RuntimeError("unexpected test container identity")
    existing = docker("exec", CONTAINER, "psql", "-U", USER, "-d", "postgres", "-tAc", "SELECT 1 FROM pg_database WHERE datname='climate_safety_4b9_test'")
    if existing:
        raise RuntimeError("test database already exists; preserve it and choose a new reviewed test target")
    if not existing:
        docker("exec", CONTAINER, "createdb", "-U", USER, DATABASE)
        docker("exec", CONTAINER, "psql", "-v", "ON_ERROR_STOP=1", "-U", USER, "-d", DATABASE, "-c", "CREATE EXTENSION IF NOT EXISTS postgis")
    url = URL.create("postgresql+psycopg", username=USER, password=env["POSTGRES_PASSWORD"], host="127.0.0.1", port=int(ports[0]["HostPort"]), database=DATABASE)
    run_env = os.environ.copy()
    run_env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "f78a9b0c1d2e"], env=run_env, capture_output=True, text=True)
    report = {"database": DATABASE, "container": CONTAINER, "migration_returncode": result.returncode,
              "migration_log": (result.stdout + "\n" + result.stderr).replace(env["POSTGRES_PASSWORD"], "[redacted]"),
              "historical_ingestion_test": "NOT_RUN", "production_database_writes": False}
    if result.returncode == 0:
        engine = create_engine(url)
        with engine.connect() as conn:
            report["alembic_revision"] = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            report["checkpoint_table_exists"] = conn.execute(text("SELECT to_regclass('public.climate_historical_import_checkpoints') IS NOT NULL")).scalar_one()
        if report["alembic_revision"] != "f78a9b0c1d2e" or not report["checkpoint_table_exists"]:
            raise RuntimeError("unexpected migration state; refusing test writes")
        verified = load_verified()
        def fingerprints(conn):
            queries = {
                'pilot': "SELECT o.* FROM climate_daily_observations o JOIN climate_dataset_versions v ON v.id=o.dataset_version_id WHERE v.product_version='synthetic_pilot'",
                'pilot_version': "SELECT * FROM climate_dataset_versions WHERE product_version='synthetic_pilot'",
                'pilot_grid': "SELECT g.* FROM climate_grid_cells g JOIN climate_dataset_versions v ON v.id=g.dataset_version_id WHERE v.product_version='synthetic_pilot'",
                'weather': 'SELECT * FROM weather_readings',
                'weather_stations': 'SELECT * FROM weather_stations',
                'monthly': 'SELECT * FROM district_weather_monthly',
                'forecasts': 'SELECT * FROM weather_forecasts',
                'mappings': 'SELECT * FROM climate_attraction_mappings',
            }
            result = {}
            for label, query in queries.items():
                rows = conn.execute(text('SELECT to_jsonb(r)::text FROM (' + query + ') r ORDER BY to_jsonb(r)::text COLLATE "C"')).scalars().all()
                h = hashlib.sha256()
                for row in rows:
                    raw = row.encode('utf-8')
                    h.update(len(raw).to_bytes(8, 'big')); h.update(raw)
                result[label] = {'count': len(rows), 'sha256': h.hexdigest()}
            return result
        with engine.begin() as conn:
            baseline = {table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in ("attractions", "weather_readings", "climate_daily_observations")}
            if any(baseline.values()):
                raise RuntimeError("test database not empty")
            pilot = conn.execute(ClimateDatasetVersion.__table__.insert().returning(ClimateDatasetVersion.id), dict(source_name='test', provider_name='test', product_name='test', product_version='synthetic_pilot', source_url='https://example.invalid', license_review_status='test', retrieved_at=datetime.now(timezone.utc), source_units_json={}, normalized_units_json={})).scalar_one()
            pilot_grid = conn.execute(ClimateGridCell.__table__.insert().returning(ClimateGridCell.id), dict(dataset_version_id=pilot, source_grid_identifier='pilot', latitude=6.0, longitude=80.0, geometry='SRID=4326;POINT(80 6)', spatial_resolution='test', metadata_json={})).scalar_one()
            conn.execute(ClimateDailyObservation.__table__.insert(), dict(dataset_version_id=pilot, grid_cell_id=pilot_grid, observation_date=date(2024,1,1), quality_status='test', source_record_hash='0'*64, created_at=datetime.now(timezone.utc)))
            conn.execute(text("INSERT INTO weather_stations(station_id,station_name,created_at,updated_at) VALUES ('test','test',now(),now())"))
            conn.execute(text("INSERT INTO weather_readings(station_id,station_name,observation_date,source) VALUES ('test','test','2024-01-01','test')"))
            district = conn.execute(text("INSERT INTO districts(name,province,is_active,created_at,updated_at,boundary) VALUES ('Test district','Test',true,now(),now(),ST_GeomFromText('MULTIPOLYGON(((80 6,81 6,81 7,80 7,80 6)))',4326)) RETURNING id")).scalar_one()
            attraction = conn.execute(text("INSERT INTO attractions(name,slug,is_active,created_at,updated_at) VALUES ('Synthetic','synthetic',true,now(),now()) RETURNING id")).scalar_one()
            conn.execute(text("INSERT INTO climate_attraction_mappings(attraction_id,dataset_version_id,grid_cell_id,mapping_method,geographic_confidence,created_at) VALUES (:attraction,:pilot,:grid,'test','test',now())"), {'attraction': attraction, 'pilot': pilot, 'grid': pilot_grid})
            conn.execute(text("INSERT INTO district_weather_monthly(district_id,observation_date,created_at,updated_at) VALUES (:district,'2024-01-01',now(),now())"), {'district': district})
            conn.execute(text("INSERT INTO weather_model_runs(run_id,district_id,target,model_name,training_start,training_cutoff,latest_calendar_month,latest_observed_month,latest_month_missing,training_observations,forecast_horizon_months,validation_gate_passed,production_approved,parameters,status,created_at_utc) VALUES ('synthetic',:district,'rainfall','test','2023-01-01','2023-12-01','2023-12-01','2023-12-01',false,12,1,false,false,'{}','test',now())"), {'district': district})
            conn.execute(text("INSERT INTO weather_forecasts(run_id,forecast_month,predicted_value,raw_prediction,created_at) VALUES ('synthetic','2024-01-01',1,1,now())"))
            ids = {}
            for batch, version in VERSIONS.items():
                ids[batch] = conn.execute(ClimateDatasetVersion.__table__.insert().returning(ClimateDatasetVersion.id), dict(
                    source_name="NASA POWER", provider_name="NASA", product_name="POWER Daily", product_version=version,
                    source_url="https://power.larc.nasa.gov/", license_review_status="test_only", retrieved_at=datetime.now(timezone.utc), source_units_json={}, normalized_units_json={})).scalar_one()
            grids = {}
            for sample, _, location, _ in verified:
                grids[sample["sample_id"]] = conn.execute(ClimateGridCell.__table__.insert().returning(ClimateGridCell.id), dict(
                    dataset_version_id=ids[sample["batch"]], source_grid_identifier=sample["sample_id"], latitude=location["latitude"], longitude=location["longitude"],
                    geometry=f"SRID=4326;POINT({location['longitude']} {location['latitude']})", spatial_resolution="representative_only",
                    metadata_json={"source_sha256": sample["original_acquisition_sha256"]})).scalar_one()
            before = fingerprints(conn)
        dates = {date(int(x[:4]), int(x[4:6]), int(x[6:])) for x in EXPECTED}
        def run_sample(item, hook=None):
            sample, records, _, _ = item
            return import_sample(engine, dataset_version_id=ids[sample["batch"]], grid_cell_id=grids[sample["sample_id"]], sample_id=sample["sample_id"],
                                 source_sha256=sample["original_acquisition_sha256"], records=records, expected_dates=dates, _before_checkpoint=hook)
        def interrupt():
            raise RuntimeError("isolated rollback test")
        try:
            run_sample(verified[0], interrupt)
            raise AssertionError("failure injection did not execute")
        except RuntimeError as exc:
            if str(exc) != "isolated rollback test":
                raise
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM climate_daily_observations")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM climate_historical_import_checkpoints")).scalar_one() == 0
        inserted = sum(run_sample(sample)["inserted"] for sample in verified)
        unchanged = sum(run_sample(sample)["unchanged"] for sample in verified)
        with engine.connect() as conn:
            counts = dict(conn.execute(text("SELECT v.product_version, count(o.id) FROM climate_dataset_versions v JOIN climate_daily_observations o ON v.id=o.dataset_version_id WHERE v.product_version <> 'synthetic_pilot' GROUP BY v.product_version")).all())
            assert counts == {VERSIONS["batch01"]: 17532, VERSIONS["batch02"]: 146100}
            assert conn.execute(text("SELECT count(*) FROM climate_historical_import_checkpoints")).scalar_one() == 28
            assert conn.execute(text("SELECT count(*) FROM attractions")).scalar_one() == 1
            after = fingerprints(conn)
            assert before == after
        assert inserted == unchanged == 163632
        report.update(status="CHECKPOINT_MIGRATION_AND_IMPORT_TEST_PASSED", historical_ingestion_test="PASSED",
                      inserted=inserted, repeat_unchanged=unchanged, batch_counts=counts, checkpoints=28, rollback_verified=True,
                      limitation="production migration and historical imports were not performed; production guard integration, named-collation failure and inconsistent checkpoint tests were not covered")
        report['content_preservation'] = {'before': before, 'after': after, 'equal': before == after}
        engine.dispose()
    else:
        report["status"] = "MIGRATION_CHAIN_FAILED"
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "migration_log"}, indent=2))
    if result.returncode:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
