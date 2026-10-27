"""Run a NASA historical import test in a newly created loopback-only container.

This harness cannot select an existing database or production host. It never
deletes the disposable test container, which remains available for inspection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL

from app.climate.historical_executor import checkpoints, import_sample
from app.climate.providers.nasa_power import normalize
from app.models.climate import ClimateDailyObservation, ClimateDatasetVersion, ClimateGridCell
from scripts.audit_stage12_4b5_historical import EXPECTED, audit_sample, decode_acquisition_output

CONTAINER = "wandaraya-climate-executor-integration-test"
DATABASE = "climate_executor_isolated_test"
USER = "climate_executor_test"
MANIFEST = Path("data/reports/stage12_4b5_source_provenance.json")
REPORT = Path("data/reports/stage12_4b5_postgresql_executor_test.json")
VERSIONS = {"batch01": "nasa_power_daily_v2.10.0_historical_2010_2025_batch01",
            "batch02": "nasa_power_daily_v2.10.0_historical_2010_2025_batch02"}


def docker(*args, env=None):
    return subprocess.run(["docker", *args], check=True, text=True, capture_output=True, env=env).stdout.strip()


def load_verified():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    b1 = json.loads(Path("data/reports/stage12_4b3_historical_manifest.json").read_text(encoding="utf-8"))
    evidence_path = Path(manifest["evidence_file"].replace('\\', '/'))
    evidence = evidence_path.read_bytes()
    if hashlib.sha256(evidence).hexdigest() != manifest["evidence_sha256"]:
        raise ValueError("acquisition evidence hash mismatch")
    b2 = decode_acquisition_output(evidence_path)
    hashes = {x["sample_id"]: x["checksum_sha256"] for x in b1["samples"]}
    hashes.update({x["sample_id"]: x["checksum_sha256"] for x in b2["results"]})
    samples = manifest["samples"]
    if len(samples) != 28 or len({s["sample_id"] for s in samples}) != 28 or set(hashes) != {s["sample_id"] for s in samples}:
        raise ValueError("unexpected source scope")
    if {b: sum(s["batch"] == b for s in samples) for b in VERSIONS} != {"batch01": 3, "batch02": 25}:
        raise ValueError("unexpected batch scope")
    verified = []
    for sample in samples:
        digest = hashes[sample["sample_id"]]
        if sample["original_acquisition_sha256"] != digest:
            raise ValueError("provenance conflicts with original acquisition evidence")
        audit = audit_sample(sample, digest)
        if audit["structural_errors"] or audit["temperature_min_exceeds_max"] or any(p["invalid"] or p["missing"] for p in audit["parameters"].values()):
            raise ValueError("source quality check failed: " + sample["sample_id"])
        raw = Path(sample["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("source changed after validation")
        records, metadata = normalize(json.loads(raw))
        processed = json.loads(Path(sample["raw_file"].replace("raw/nasa_power/", "processed/nasa_power/")).read_text(encoding="utf-8"))
        if processed["records"] != records or processed["metadata"] != metadata:
            raise ValueError("processed source mismatch")
        location = processed.get("location") or processed.get("sample")
        if not location or "latitude" not in location or "longitude" not in location:
            raise ValueError("sample location missing")
        verified.append((sample, records, location, metadata))
    return verified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-isolated-test", action="store_true")
    parser.add_argument("--confirm-isolated-test", action="store_true")
    args = parser.parse_args()
    if not (args.execute_isolated_test and args.confirm_isolated_test):
        raise SystemExit("Both isolated-test flags required; production execution is not supported")
    verified = load_verified()
    if subprocess.run(["docker", "inspect", CONTAINER], capture_output=True).returncode == 0:
        raise SystemExit("Test container name already exists; refusing reuse or removal")
    password = secrets.token_urlsafe(32)
    env = os.environ.copy()
    env["POSTGRES_PASSWORD"] = password
    docker("run", "-d", "--pull", "never", "--name", CONTAINER, "--network", "bridge",
           "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD", "-e", f"POSTGRES_USER={USER}",
           "-e", f"POSTGRES_DB={DATABASE}", "postgis/postgis:17-3.5", env=env)
    info = json.loads(docker("inspect", CONTAINER))[0]
    bindings = info["NetworkSettings"]["Ports"]["5432/tcp"]
    if len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
        raise RuntimeError("test container port is not loopback-only")
    port = int(bindings[0]["HostPort"])
    engine = create_engine(URL.create("postgresql+psycopg", username=USER, password=password,
                                      host="127.0.0.1", port=port, database=DATABASE))
    for attempt in range(60):
        try:
            with engine.connect() as conn:
                assert conn.execute(text("SELECT current_database(), current_user")).one() == (DATABASE, USER)
            break
        except Exception:
            if attempt == 59:
                raise
            time.sleep(1)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        ClimateDatasetVersion.__table__.create(conn)
        ClimateGridCell.__table__.create(conn)
        ClimateDailyObservation.__table__.create(conn)
        checkpoints.create(conn)
        ids = {}
        for batch, version in VERSIONS.items():
            ids[batch] = conn.execute(ClimateDatasetVersion.__table__.insert().returning(ClimateDatasetVersion.id), dict(
                source_name="NASA POWER", provider_name="NASA", product_name="POWER Daily", product_version=version,
                source_url="https://power.larc.nasa.gov/", license_review_status="test_only",
                retrieved_at=datetime.now(timezone.utc), source_units_json={}, normalized_units_json={})).scalar_one()
        pilot = conn.execute(ClimateDatasetVersion.__table__.insert().returning(ClimateDatasetVersion.id), dict(
            source_name="TEST SENTINEL", provider_name="TEST", product_name="TEST", product_version="nasa_power_daily_v2.10.0_2024_pilot",
            source_url="test-only", license_review_status="test_only", retrieved_at=datetime.now(timezone.utc),
            source_units_json={}, normalized_units_json={})).scalar_one()
        grids = {}
        for sample, _, location, _ in verified:
            grids[sample["sample_id"]] = conn.execute(ClimateGridCell.__table__.insert().returning(ClimateGridCell.id), dict(
                dataset_version_id=ids[sample["batch"]], source_grid_identifier=sample["sample_id"],
                latitude=location["latitude"], longitude=location["longitude"],
                geometry=f"SRID=4326;POINT({location['longitude']} {location['latitude']})",
                spatial_resolution="representative_only", metadata_json={"source_sha256": sample["original_acquisition_sha256"]})).scalar_one()
    dates = {date(int(x[:4]), int(x[4:6]), int(x[6:])) for x in EXPECTED}
    def run_sample(item, hook=None):
        s, records, _, _ = item
        return import_sample(engine, dataset_version_id=ids[s["batch"]], grid_cell_id=grids[s["sample_id"]],
                             sample_id=s["sample_id"], source_sha256=s["original_acquisition_sha256"],
                             records=records, expected_dates=dates, _before_checkpoint=hook)
    def interrupt():
        raise RuntimeError("intentional interruption")
    try:
        run_sample(verified[0], interrupt)
        raise AssertionError("injected failure did not trigger")
    except RuntimeError as exc:
        if str(exc) != "intentional interruption":
            raise
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM climate_daily_observations")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM climate_historical_import_checkpoints")).scalar_one() == 0
    inserted = sum(run_sample(s)["inserted"] for s in verified)
    repeated = sum(run_sample(s)["unchanged"] for s in verified)
    with engine.connect() as conn:
        counts = dict(conn.execute(text("SELECT v.product_version, count(o.id) FROM climate_dataset_versions v LEFT JOIN climate_daily_observations o ON o.dataset_version_id=v.id GROUP BY v.product_version")).all())
        assert counts[VERSIONS["batch01"]] == 17532 and counts[VERSIONS["batch02"]] == 146100
        assert counts["nasa_power_daily_v2.10.0_2024_pilot"] == 0
        assert conn.execute(text("SELECT count(*) FROM climate_historical_import_checkpoints")).scalar_one() == 28
        assert conn.execute(text("SELECT count(*) FROM (SELECT dataset_version_id, grid_cell_id, observation_date FROM climate_daily_observations GROUP BY 1,2,3 HAVING count(*) > 1) d")).scalar_one() == 0
    assert inserted == repeated == 163632
    report = {"status": "ISOLATED_POSTGRESQL_IMPORT_TEST_PASSED", "test_container": CONTAINER,
              "database": DATABASE, "sample_count": 28, "inserted": inserted, "repeat_unchanged": repeated,
              "batch_counts": counts, "rollback_verified": True, "resume_verified": True,
              "checkpoints": 28, "production_database_writes": False, "qdrant_writes": False,
              "pilot_note": "Isolated synthetic pilot sentinel; production pilot was not touched or read",
              "limitations": ["isolated schema created from ORM tables, not a production migration", "production collation unresolved", "production apply remains disabled"]}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
