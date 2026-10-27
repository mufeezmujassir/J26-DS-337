"""Read-only, repeatable-read content and named-collation evidence collection.

Run inside the API container. No production writes or external API calls.
The JSON row representation is PostgreSQL 17 jsonb text, with session timezone
set to UTC. All columns, including timestamps, are included; do not compare
across PostgreSQL versions or change this serialization without a new baseline.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from app.database import engine

ROOT = Path("data/reports")
PILOT = "nasa_power_daily_v2.10.0_2024_pilot"
TABLES = {
    "pilot_observations": "SELECT o.* FROM climate_daily_observations o JOIN climate_dataset_versions v ON v.id=o.dataset_version_id WHERE v.product_version=:pilot",
    "pilot_dataset": "SELECT * FROM climate_dataset_versions WHERE product_version=:pilot",
    "pilot_grid_cells": "SELECT g.* FROM climate_grid_cells g JOIN climate_dataset_versions v ON v.id=g.dataset_version_id WHERE v.product_version=:pilot",
    "climate_attraction_mappings": "SELECT * FROM climate_attraction_mappings",
    "weather_readings": "SELECT * FROM weather_readings",
    "district_weather_monthly": "SELECT * FROM district_weather_monthly",
    "weather_forecasts": "SELECT * FROM weather_forecasts",
}


async def main():
    async with engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            await conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            identity = (await conn.execute(text("SELECT current_database() AS database, current_user AS username, current_setting('server_version') AS server_version, inet_server_addr()::text AS address, inet_server_port() AS port"))).mappings().one()
            if identity["database"] != "wandaraya":
                raise RuntimeError("Unexpected database; refusing baseline")
            baseline = {"database": identity["database"], "format": "postgresql-17-jsonb-text-utc-sorted-C-v1", "excluded_columns": [], "tables": {}}
            for name, query in TABLES.items():
                rows = await conn.stream(text("SELECT to_jsonb(r)::text AS row FROM (" + query + ") r ORDER BY to_jsonb(r)::text COLLATE \"C\""), {"pilot": PILOT})
                digest = hashlib.sha256()
                count = 0
                async for row in rows:
                    payload = row.row.encode("utf-8")
                    digest.update(len(payload).to_bytes(8, "big"))
                    digest.update(payload)
                    count += 1
                baseline["tables"][name] = {"rows": count, "sha256": digest.hexdigest()}
            mismatches = (await conn.execute(text("SELECT c.oid, n.nspname AS schema_name, c.collname, c.collprovider, c.collversion AS recorded, pg_collation_actual_version(c.oid) AS actual FROM pg_collation c JOIN pg_namespace n ON n.oid=c.collnamespace WHERE c.collversion IS NOT NULL AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid) ORDER BY c.oid"))).mappings().all()
            index_refs = (await conn.execute(text("SELECT DISTINCT n.nspname AS schema_name, t.relname AS table_name, idx.relname AS index_name, i.indisunique, c.collname, pg_get_indexdef(i.indexrelid) AS definition FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace JOIN LATERAL unnest(i.indcollation) k(oid) ON k.oid<>0 JOIN pg_collation c ON c.oid=k.oid WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.collversion IS NOT NULL AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)"))).mappings().all()
            column_refs = (await conn.execute(text("SELECT n.nspname AS schema_name, t.relname AS table_name, a.attname AS column_name, c.collname FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_collation c ON c.oid=a.attcollation WHERE a.attnum>0 AND NOT a.attisdropped AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.collversion IS NOT NULL AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)"))).mappings().all()
            deps = (await conn.execute(text("SELECT c.collname, d.classid::regclass::text AS dependent_catalog, d.objid, d.objsubid, d.deptype, pg_describe_object(d.classid,d.objid,d.objsubid) AS object_description FROM pg_depend d JOIN pg_collation c ON c.oid=d.refobjid WHERE d.refclassid='pg_collation'::regclass AND c.collversion IS NOT NULL AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid) ORDER BY 1,2,3"))).mappings().all()
            collation = {"database": identity["database"], "mismatch_count": len(mismatches), "mismatches": [dict(x) for x in mismatches], "user_index_references": [dict(x) for x in index_refs], "user_column_references": [dict(x) for x in column_refs], "catalog_dependencies": [dict(x) for x in deps], "limitations": ["Dynamic SQL, client-side collation choices and textual SQL bodies are not established by catalog scans.", "Index constraints and expression dependencies must be reviewed via their index and pg_depend references."]}
    await engine.dispose()
    (ROOT / "stage12_4b7_content_baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    (ROOT / "stage12_4b7_named_collation_dependencies.json").write_text(json.dumps(collation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"database": identity["database"], "baseline_tables": len(baseline["tables"]), "mismatches": len(mismatches), "index_refs": len(index_refs), "column_refs": len(column_refs), "dependencies": len(deps), "postgresql_writes": False}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
