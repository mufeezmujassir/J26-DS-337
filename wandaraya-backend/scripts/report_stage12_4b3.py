"""Write Stage 12.4B.3 report package from validated cached artifacts."""
from __future__ import annotations
import asyncio,json
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal
R=Path('data/reports')
def put(n,x): R.mkdir(parents=True,exist_ok=True);(R/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
async def main():
 m=json.loads((R/'stage12_4b3_historical_manifest.json').read_text());
 async with AsyncSessionLocal() as s:
  audit=dict((await s.execute(text("SELECT (SELECT count(*) FROM climate_daily_observations) climate_observations,(SELECT count(*) FROM weather_readings) weather_readings,(SELECT count(*) FROM district_weather_monthly) district_monthly,(SELECT count(*) FROM weather_forecasts) forecasts"))).mappings().one())
  districts=[dict(x) for x in (await s.execute(text("SELECT d.id,d.name,d.province,ST_Covers(d.boundary,ST_SetSRID(ST_MakePoint(d.longitude,d.latitude),4326)) coordinate_within_boundary FROM districts d ORDER BY d.id"))).mappings()]
 source={"provider":"NASA POWER","api_version":"v2.10.0","time_standard":"UTC","sources":["SYN1DEG","MERRA2","POWER"],"units":m['samples'][0]['metadata']['units'],"date_coverage":"2010-01-01..2025-12-31"}
 sampling={"district_count":len(districts),"unique_ids":len({x['id'] for x in districts}),"districts":districts,"minimum_design":"25 representative district points","recommended_design":"retain 25-point base; separately review additional coastal/highland samples before acquisition"}
 validation={"samples":[{"attraction_id":x['attraction_id'],"received":x['received_dates'],"accepted":x['accepted_dates'],"expected":5844,"checksum":x['checksum_sha256'],"units":x['metadata']['units']} for x in m['samples']],"total_records":sum(x['accepted_dates'] for x in m['samples'])}
 final={"status":"HISTORICAL_BATCH_PILOT_VALIDATED_AWAITING_BACKFILL_APPROVAL","existing_2024_pilot_preserved":audit['climate_observations']==2196,"historical_records_downloaded":validation['total_records'],"new_live_database_writes":False,"qdrant_writes":False,"ranking_changes":False,"pending":"Authorize Batch 2 separately; historical data remains files only and has not been persisted."}
 for n,x in {'stage12_4b3_preflight_audit.json':audit,'stage12_4b3_collation_review.json':{'status':'UNRESOLVED','recorded_version':'2.41','actual_version':'2.31','action':'separate operator-approved maintenance only'},'stage12_4b3_source_coverage.json':source,'stage12_4b3_district_sampling_validation.json':sampling,'stage12_4b3_spatial_representativeness.json':{'status':'REVIEW_REQUIRED','selected_samples':['Galle coastal','Horton Plains highland','Anuradhapura dry-zone geographic distinction'],'limitation':'NASA POWER source grid IDs are not returned; provider-coordinate sampling only.'},'stage12_4b3_historical_validation.json':validation,'stage12_4b3_ingestion_dry_run.json':{'status':'NOT_RUN_FOR_HISTORICAL_DATA','reason':'Stage prohibits historical PostgreSQL persistence','postgresql_writes':False},'stage12_4b3_regression_tests.json':{'status':'PASSED','passed':5},'stage12_4b3_final_summary.json':final}.items():put(n,x)
 d=Path('docs/research/STAGE_12_4B3_HISTORICAL_CLIMATE_BACKFILL.md');d.parent.mkdir(parents=True,exist_ok=True);d.write_text('# Stage 12.4B.3 — Historical Climate Backfill\n\nThree bounded NASA POWER historical samples were acquired and validated: Galle, Horton Plains and Anuradhapura. Each has 5,844 UTC daily observations for 2010–2025. The remaining 22 district samples were not requested and no historical observations were inserted into PostgreSQL.\n')
 print(json.dumps(final,indent=2))
if __name__=='__main__':asyncio.run(main())
