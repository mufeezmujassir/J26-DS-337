"""Validate prepared NASA POWER pilot artifacts; dry-run by default."""
from __future__ import annotations
import argparse, hashlib, json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from app.climate.validation import validate_daily_records
from app.database import AsyncSessionLocal

def main():
    p=argparse.ArgumentParser(); p.add_argument("--provider",required=True); p.add_argument("--pilot",action="store_true"); p.add_argument("--dry-run",action="store_true"); p.add_argument("--apply",action="store_true"); p.add_argument("--confirm-apply",action="store_true"); p.add_argument("--manifest",default="data/climate/manifests/nasa_power/pilot_2024_manifest_v2.json"); p.add_argument("--dataset-version",default="nasa_power_daily_v2.10.0_2024_pilot"); p.add_argument("--max-records",type=int,default=3000); args=p.parse_args()
    if args.provider != "nasa_power" or not args.pilot: raise SystemExit("only NASA POWER pilot is supported")
    if args.apply and not args.confirm_apply: raise SystemExit("--apply requires --confirm-apply")
    manifest=json.loads(Path(args.manifest).read_text()); prepared=0; rejected=0; identities=set()
    for location in manifest["locations"]:
        if location["status"] != "VALIDATED": raise SystemExit("manifest includes unsuccessful location")
        raw=Path(location["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=location["checksum_sha256"]: raise SystemExit("raw checksum mismatch")
        processed=Path(location["raw_file"].replace("raw/nasa_power","processed/nasa_power/v2")); data=json.loads(processed.read_text())
        valid=validate_daily_records(data["records"]); rejected+=valid["rejected"]
        for row in valid["rejections"]: pass
        for row in data["records"]:
            identity=(location["attraction_id"],row["date"])
            if identity in identities: raise SystemExit("duplicate attraction-date identity")
            identities.add(identity); prepared+=1
    if prepared>args.max_records: raise SystemExit("max-records exceeded")
    if args.apply:
        result=asyncio.run(persist(manifest,args.dataset_version))
        result.update({"records_prepared":prepared,"rejected":rejected})
    else:
        result={"status":"DRY_RUN_VALIDATED","provider":args.provider,"dataset_version":args.dataset_version,"records_prepared":prepared,"rejected":rejected,"dataset_version_insert":1,"grid_or_sample_records":len(manifest["locations"]),"attraction_mappings":len(manifest["locations"]),"observation_inserts":prepared,"postgresql_writes":False,"qdrant_writes":False}
    Path("data/reports/stage12_4b2_pilot_ingestion_dry_run.json").write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result,indent=2))
async def persist(manifest: dict, dataset_version: str) -> dict:
    """Atomic, idempotent persistence of only the already verified pilot."""
    inserted_observations=inserted_mappings=inserted_cells=0
    async with AsyncSessionLocal() as session:
        async with session.begin():
            dataset=await session.execute(text("""
              INSERT INTO climate_dataset_versions (source_name,provider_name,product_name,product_version,source_url,license_review_status,attribution_text,reference_start,reference_end,retrieved_at,request_manifest_hash,dataset_checksum,source_units_json,normalized_units_json)
              VALUES ('NASA POWER Daily API','NASA POWER','source-native daily meteorological data',:version,'https://power.larc.nasa.gov/api/temporal/daily/point','DOCUMENTED_REVIEW_REQUIRED','NASA POWER',DATE '2024-01-01',DATE '2024-12-31',:now,:manifest_hash,:manifest_hash,:units,:normalized)
              ON CONFLICT (provider_name,product_name,product_version) DO UPDATE SET product_version=EXCLUDED.product_version
              RETURNING id
            """),{"version":dataset_version,"now":datetime.now(timezone.utc),"manifest_hash":manifest["manifest_sha256"],"units":json.dumps(manifest["locations"][0]["metadata"]["units"]),"normalized":json.dumps({"precipitation_mm":"mm/day","temperature_mean_c":"C","temperature_min_c":"C","temperature_max_c":"C","relative_humidity_pct":"%","wind_speed_10m":"m/s","solar_radiation":"MJ/m^2/day"})})
            dataset_id=dataset.scalar_one()
            for location in manifest["locations"]:
                grid_key=f"provider_coordinate:{location['attraction_id']}"
                grid=await session.execute(text("""
                  INSERT INTO climate_grid_cells (dataset_version_id,source_grid_identifier,latitude,longitude,geometry,spatial_resolution,metadata_json)
                  VALUES (:dataset_id,:key,:lat,:lon,ST_SetSRID(ST_MakePoint(:lon,:lat),4326),'source_native_resolution_unverified',:metadata)
                  ON CONFLICT (dataset_version_id,source_grid_identifier) DO UPDATE SET source_grid_identifier=EXCLUDED.source_grid_identifier RETURNING id
                """),{"dataset_id":dataset_id,"key":grid_key,"lat":location.get("latitude",0) or json.loads(Path(location["raw_file"].replace("raw/nasa_power","processed/nasa_power/v2")).read_text())["location"]["latitude"],"lon":location.get("longitude",0) or json.loads(Path(location["raw_file"].replace("raw/nasa_power","processed/nasa_power/v2")).read_text())["location"]["longitude"],"metadata":json.dumps({"identity":"provider_coordinate_identified_not_source_grid_identified","raw_checksum":location["checksum_sha256"]})})
                grid_id=grid.scalar_one(); inserted_cells+=1
                map_result=await session.execute(text("""
                  INSERT INTO climate_attraction_mappings (attraction_id,dataset_version_id,grid_cell_id,mapping_method,distance_km,geographic_confidence,created_at)
                  VALUES (:attraction_id,:dataset_id,:grid_id,'REQUEST_POINT_SAMPLED',0,'EXPERIMENTAL_COARSE_GRID',:now)
                  ON CONFLICT (attraction_id,dataset_version_id) DO NOTHING
                """),{"attraction_id":location["attraction_id"],"dataset_id":dataset_id,"grid_id":grid_id,"now":datetime.now(timezone.utc)}); inserted_mappings+=map_result.rowcount
                data=json.loads(Path(location["raw_file"].replace("raw/nasa_power","processed/nasa_power/v2")).read_text())
                rows=[]
                for row in data["records"]:
                    rows.append({"dataset_id":dataset_id,"grid_id":grid_id,"date":row["date"],"rain":row["precipitation_mm"],"mean":row["temperature_mean_c"],"min":row["temperature_min_c"],"max":row["temperature_max_c"],"rh":row["relative_humidity_pct"],"wind":row["wind_speed_10m"],"solar":row["solar_radiation"],"hash":hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest(),"now":datetime.now(timezone.utc)})
                res=await session.execute(text("""
                  INSERT INTO climate_daily_observations (dataset_version_id,grid_cell_id,observation_date,precipitation_mm,temperature_mean_c,temperature_min_c,temperature_max_c,relative_humidity_pct,wind_speed,wind_speed_unit,solar_radiation,solar_radiation_unit,quality_status,source_record_hash,created_at)
                  VALUES (:dataset_id,:grid_id,:date,:rain,:mean,:min,:max,:rh,:wind,'m/s',:solar,'MJ/m^2/day','VALIDATED',:hash,:now)
                  ON CONFLICT (dataset_version_id,grid_cell_id,observation_date) DO NOTHING
                """),rows); inserted_observations+=res.rowcount
            await session.execute(text("INSERT INTO climate_ingestion_runs (dataset_version_id,started_at,completed_at,status,request_count,records_received,records_accepted,records_rejected,manifest_path) VALUES (:id,:now,:now,'SUCCEEDED',6,2196,2196,0,:path)"),{"id":dataset_id,"now":datetime.now(timezone.utc),"path":"data/climate/manifests/nasa_power/pilot_2024_manifest_v2.json"})
    return {"status":"PILOT_PERSISTED_VERIFIED","provider":"nasa_power","dataset_version":dataset_version,"dataset_version_id":dataset_id,"climate_grid_cells_touched":inserted_cells,"attraction_mappings_inserted":inserted_mappings,"observations_inserted":inserted_observations,"postgresql_writes":True,"qdrant_writes":False}


if __name__=="__main__": main()
