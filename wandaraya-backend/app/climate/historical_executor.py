"""Transaction primitive for historical climate imports; no production CLI.

The caller must provision the checkpoint table in an isolated database and
resolve the dataset and grid IDs beforehand. This module never opens a database
connection itself. Production use requires a reviewed migration and preflight.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone

from sqlalchemy import insert, select, text

from app.models.climate import ClimateDailyObservation, ClimateDatasetVersion, ClimateGridCell, ClimateHistoricalImportCheckpoint


HISTORICAL_VERSIONS = {
    "nasa_power_daily_v2.10.0_historical_2010_2025_batch01",
    "nasa_power_daily_v2.10.0_historical_2010_2025_batch02",
}

# Importing metadata does not create or migrate a database.
checkpoints = ClimateHistoricalImportCheckpoint.__table__

FIELDS = ("precipitation_mm", "temperature_mean_c", "temperature_min_c",
          "temperature_max_c", "relative_humidity_pct", "wind_speed_10m",
          "solar_radiation")


def canonical_records(records: list[dict]) -> list[dict]:
    """Validate and hash source-derived records, deterministically."""
    result, seen = [], set()
    for record in records:
        day = date.fromisoformat(record["date"])
        if day in seen:
            raise ValueError(f"duplicate observation date: {day}")
        seen.add(day)
        values = {}
        for field in FIELDS:
            value = record.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"invalid {field} for {day}")
            values[field] = value
        payload = {"date": day.isoformat(), **values}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        result.append((day, values, digest))
    if not result:
        raise ValueError("empty sample")
    return sorted(result, key=lambda row: row[0])


def import_sample(engine, *, dataset_version_id: int, grid_cell_id: int,
                  sample_id: str, source_sha256: str, records: list[dict],
                  expected_dates: set[date], batch_size: int = 500,
                  target_identity=None, _before_checkpoint=None) -> dict:
    """Atomically insert one verified sample and its resume checkpoint.

    Callers must independently verify the raw file's checksum and normalize it
    immediately before calling. An existing checkpoint is not blindly trusted:
    every stored observation's source hash and date is compared to the input.
    This primitive does not authorize production writes.
    """
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("invalid source SHA-256")
    if not sample_id or batch_size < 1:
        raise ValueError("invalid sample or batch size")
    rows = canonical_records(records)
    if {r[0] for r in rows} != expected_dates:
        raise ValueError("source date scope mismatch")
    if engine.dialect.name not in {"postgresql", "sqlite"}:
        raise ValueError("unsupported database dialect")
    if engine.dialect.name == "postgresql" and target_identity is None:
        # This primitive is currently for isolated testing only. A future
        # production implementation must replace this boundary with reviewed,
        # independently verified authorization and target controls.
        if engine.url.host not in {"127.0.0.1", "::1", "localhost"} or engine.url.username != "climate_executor_test" or engine.url.database not in {
            "climate_executor_isolated_test", "climate_alembic_5b_test", "climate_checkpoint_5c_test", "climate_safety_4b7_test", "climate_safety_4b8_test", "climate_safety_4b8b_test", "climate_safety_4b9_test", "climate_orchestrator_isolated_test", "climate_cli_orchestrator_isolated_test", "climate_cli_reconcile_isolated_test"
        }:
            raise ValueError("PostgreSQL target is not an approved isolated test database")
    obs = ClimateDailyObservation.__table__
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            if target_identity is not None:
                from app.climate.production_guard import verify_connection_identity
                verify_connection_identity(conn, target_identity)
            else:
                actual = conn.execute(text("SELECT current_database(), current_user")).one()
                if actual != (engine.url.database, "climate_executor_test"):
                    raise ValueError("connected PostgreSQL identity is not the approved isolated target")
        version = conn.execute(select(ClimateDatasetVersion.product_version).where(ClimateDatasetVersion.id == dataset_version_id)).scalar_one()
        if version not in HISTORICAL_VERSIONS:
            raise ValueError("dataset is not an authorized historical version")
        grid_version = conn.execute(select(ClimateGridCell.dataset_version_id).where(ClimateGridCell.id == grid_cell_id)).scalar_one()
        if grid_version != dataset_version_id:
            raise ValueError("grid belongs to a different dataset")
        existing_checkpoint = conn.execute(select(checkpoints).where(checkpoints.c.dataset_version_id == dataset_version_id, checkpoints.c.grid_cell_id == grid_cell_id)).mappings().one_or_none()
        if existing_checkpoint and (existing_checkpoint["source_sha256"] != source_sha256 or existing_checkpoint["sample_id"] != sample_id or existing_checkpoint["record_count"] != len(rows)):
            raise ValueError("checkpoint conflicts with input")
        stored = conn.execute(select(obs).where(obs.c.dataset_version_id == dataset_version_id, obs.c.grid_cell_id == grid_cell_id)).mappings().all()
        existing = {row['observation_date']: row['source_record_hash'] for row in stored}
        expected = {day: digest for day, _, digest in rows}
        if any(expected.get(day) != digest for day, digest in existing.items()):
            raise ValueError("existing observations conflict with source")
        expected_values = {day: values for day, values, _ in rows}
        for row in stored:
            values = expected_values[row['observation_date']]
            for field in FIELDS:
                column = 'wind_speed' if field == 'wind_speed_10m' else field
                if row[column] != values[field]:
                    raise ValueError("existing observation payload conflicts with source")
            if row['wind_speed_unit'] != 'm/s' or row['solar_radiation_unit'] != 'MJ/m^2/day':
                raise ValueError("existing observation units conflict with source")
        if existing_checkpoint and existing != expected:
            raise ValueError("checkpoint exists but observations are incomplete")
        pending = []
        for day, values, digest in rows:
            if day in existing:
                continue
            pending.append(dict(dataset_version_id=dataset_version_id, grid_cell_id=grid_cell_id,
                observation_date=day, precipitation_mm=values["precipitation_mm"],
                temperature_mean_c=values["temperature_mean_c"], temperature_min_c=values["temperature_min_c"],
                temperature_max_c=values["temperature_max_c"], relative_humidity_pct=values["relative_humidity_pct"],
                wind_speed=values["wind_speed_10m"], wind_speed_unit="m/s", solar_radiation=values["solar_radiation"],
                solar_radiation_unit="MJ/m^2/day", quality_status="validated", source_record_hash=digest,
                created_at=datetime.now(timezone.utc)))
        for offset in range(0, len(pending), batch_size):
            conn.execute(insert(obs), pending[offset:offset + batch_size])
        if _before_checkpoint:
            _before_checkpoint()  # test-only failure injection; transaction rolls back
        if not existing_checkpoint:
            conn.execute(insert(checkpoints).values(dataset_version_id=dataset_version_id, grid_cell_id=grid_cell_id,
                sample_id=sample_id, source_sha256=source_sha256, record_count=len(rows), committed_at=datetime.now(timezone.utc)))
    return {"inserted": len(pending), "unchanged": len(existing), "checkpoint_committed": True}
