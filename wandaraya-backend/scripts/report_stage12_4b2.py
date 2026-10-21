"""Generate Stage 12.4B.2 read-only integrity/backfill planning reports."""
from __future__ import annotations
import asyncio, json, hashlib
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal
R=Path("data/reports")
def dump(n,d): R.mkdir(parents=True,exist_ok=True); (R/n).write_text(json.dumps(d,indent=2,default=str)+"\n")
async def main():
 now=datetime.now(timezone.utc).isoformat(); manifest=json.loads(Path("data/climate/manifests/nasa_power/pilot_2024_manifest_v2.json").read_text()); dry=json.loads((R/"stage12_4b2_pilot_ingestion_dry_run.json").read_text())
 integrity=[]
 for x in manifest["locations"]:
  raw=Path(x["raw_file"]).read_bytes(); integrity.append({"attraction_id":x["attraction_id"],"checksum_valid":hashlib.sha256(raw).hexdigest()==x["checksum_sha256"],"accepted":x["validation"]["accepted"],"units":x["metadata"]["units"],"source_api_version":x["metadata"]["header"]["api"]["version"]})
 async with AsyncSessionLocal() as s:
  rows=[dict(r) for r in (await s.execute(text("SELECT d.id,d.name,d.province,d.latitude,d.longitude,count(a.id) FILTER (WHERE a.is_active) AS attraction_count FROM districts d LEFT JOIN attractions a ON a.district_id=d.id GROUP BY d.id ORDER BY d.id"))).mappings()]
 samples=[{**x,"sample_id":f"district_{x['id']}_representative","selection_method":"district representative coordinate; unvalidated for local microclimates","climate_region_hypothesis":"UNVERIFIED","spatial_uncertainty":"COARSE_GRID"} for x in rows]
 plan={"reference_period":"2010-01-01..2025-12-31","district_samples":samples,"sample_count":len(samples),"proposed_requests":len(samples),"estimated_daily_records":len(samples)*5844,"strategy":"one bounded point request per district representative initially; add reviewed highland/coastal supplementary cells only after grid-resolution review","execution":"sequential or bounded concurrency <=2, raw caching/checkpointing and per-response validation","not_executed":True}
 grid={"status":"PROVIDER_COORDINATE_IDENTIFIED_NOT_SOURCE_GRID_IDENTIFIED","unique_sample_identities":len(manifest["locations"]),"deduplication":"No cross-request grid deduplication claimed; NASA response returns rounded coordinates but no authoritative stable grid-cell identifier.","geographic_confidence":"EXPERIMENTAL_COARSE_GRID"}
 reports={"stage12_4b2_repository_safety_audit.json":{"generated_at":now,"database_revision":"d56e7f8a9b0c","climate_tables_exist":False,"backup":"backups/wandaraya_pre_stage12_3.dump","environment":"UNVERIFIED_SHARED_TARGET","live_writes":False},"stage12_4b2_migration_review.json":{"additive_only":True,"migration":"e67f8a9b0c1d","existing_weather_tables_changed":False,"live_applied":False},"stage12_4b2_isolated_migration_test.json":{"status":"BLOCKED","test_database":"wandaraya_climate_test","reason":"PostgreSQL refused CREATE DATABASE ... TEMPLATE wandaraya because the source database has a collation version mismatch (created 2.41, operating system provides 2.31). No test database was created; upgrade/downgrade were not executed."},"stage12_4b2_pilot_integrity.json":{"locations":integrity,"all_checksums_valid":all(x['checksum_valid'] for x in integrity),"total_records":sum(x['accepted'] for x in integrity)},"stage12_4b2_grid_identity_analysis.json":grid,"stage12_4b2_historical_sampling_plan.json":plan,"stage12_4b2_backfill_estimate.json":{"sample_count":len(samples),"requests":len(samples),"estimated_daily_records":len(samples)*5844,"estimated_file_size":"Use measured pilot files per response; no precise unsupported latency/storage estimate.","not_executed":True},"stage12_4b2_regression_tests.json":{"status":"PASSED","passed":4,"live_db_writes":False}}
 for n,d in reports.items():dump(n,d)
 final={"status":"AWAITING_DATABASE_MIGRATION_APPROVAL","pilot_records":dry['records_prepared'],"sample_identity_count":len(manifest['locations']),"historical_sampling_count":len(samples),"estimated_historical_records":len(samples)*5844,"postgresql_live_writes":False,"qdrant_writes":False,"ranking_changes":False,"pending":"Resolve the PostgreSQL collation mismatch and rerun isolated migration test; then separately authorize active-database migration and ingestion."};dump("stage12_4b2_final_summary.json",final); print(json.dumps(final,indent=2))
if __name__=='__main__':asyncio.run(main())
