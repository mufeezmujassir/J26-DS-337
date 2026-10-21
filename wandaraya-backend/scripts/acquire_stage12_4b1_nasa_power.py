"""Bounded NASA POWER 2024 pilot acquisition; never writes PostgreSQL."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import date, datetime, timezone
from pathlib import Path
from app.climate.providers.nasa_power import NasaPowerRequest, fetch, normalize
from app.climate.validation import validate_daily_records

REPORT=Path("data/reports"); ROOT=Path("data/climate")
def emit(name,obj): REPORT.mkdir(parents=True,exist_ok=True); (REPORT/name).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")
def save_once(path,content):
    digest=hashlib.sha256(content).hexdigest(); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise RuntimeError(f"refusing checksum-changing overwrite: {path}")
    if not path.exists(): path.write_bytes(content)
    return digest
def main():
    p=argparse.ArgumentParser(); p.add_argument("--pilot",action="store_true"); p.add_argument("--dry-run",action="store_true"); p.add_argument("--provider",default="nasa_power"); args=p.parse_args()
    if args.provider!="nasa_power" or not args.pilot: raise SystemExit("only --provider nasa_power --pilot is supported")
    pilot=json.loads((REPORT/"stage12_4b_pilot_locations.json").read_text(encoding="utf-8"))["locations"]
    start,end=date(2024,1,1),date(2024,12,31)
    base={"provider":"NASA POWER","underlying_product":"as returned in API metadata; not inferred as ERA5-Land","period":{"start":str(start),"end":str(end)},"time_standard":"UTC","database_writes":False,"qdrant_writes":False,"production_ranking_changed":False,"real_api_data":not args.dry_run}
    if args.dry_run:
        report={**base,"status":"DRY_RUN","planned_requests":len(pilot),"raw_files_written":False}; emit("stage12_4b1_nasa_acquisition.json",report); emit("stage12_4b1_nasa_ingestion_dry_run.json",{**report,"intended_inserts":len(pilot)*366,"writes":False}); print(json.dumps(report,indent=2)); return
    outcomes=[]
    # Mandatory single-location gate before the remaining five requests.
    for location in pilot:
        request=NasaPowerRequest(location["latitude"],location["longitude"],start,end)
        try:
            raw_name=f"nasa_power_{location['id']}_{start:%Y%m%d}_{end:%Y%m%d}.json"; raw_path=ROOT/"raw/nasa_power"/raw_name
            if raw_path.exists():
                raw=raw_path.read_bytes(); payload=json.loads(raw)
            else:
                payload,raw=fetch(request)
            checksum=save_once(raw_path,raw)
            records,metadata=normalize(payload); validation=validate_daily_records(records)
            if validation["accepted"] != 366: raise RuntimeError(f"validation gate accepted={validation['accepted']}")
            # Version the normalized representation separately.  Raw source
            # responses are immutable and never overwritten.
            processed=json.dumps({"location":location,"records":records,"metadata":metadata},sort_keys=True,indent=2).encode(); save_once(ROOT/"processed/nasa_power/v2"/raw_name,processed)
            outcomes.append({"attraction_id":location["id"],"name":location["name"],"status":"VALIDATED","request_url":request.url(),"raw_file":str(ROOT/"raw/nasa_power"/raw_name),"checksum_sha256":checksum,"validation":validation,"metadata":metadata})
        except Exception as exc:
            outcomes.append({"attraction_id":location["id"],"name":location["name"],"status":"FAILED","error":str(exc)})
            break
    manifest={**base,"status":"NASA_PILOT_VALIDATED_AWAITING_DB_APPROVAL" if len(outcomes)==len(pilot) and all(x["status"]=="VALIDATED" for x in outcomes) else "NASA_PILOT_PARTIALLY_VALIDATED","requests_attempted":len(outcomes),"locations":outcomes}
    manifest_bytes=json.dumps(manifest,sort_keys=True,default=str).encode(); manifest["manifest_sha256"]=hashlib.sha256(manifest_bytes).hexdigest()
    # A normalized-output revision must not rewrite the original immutable
    # manifest.  Store it as a new, explicit processing revision instead.
    save_once(ROOT/"manifests/nasa_power/pilot_2024_manifest_v2.json",json.dumps(manifest,indent=2,default=str).encode())
    emit("stage12_4b1_nasa_acquisition.json",manifest); emit("stage12_4b1_nasa_validation.json",{"real_api_data":True,"outcomes":outcomes}); emit("stage12_4b1_nasa_ingestion_dry_run.json",{"status":"DRY_RUN","records_prepared":sum(x.get("validation",{}).get("accepted",0) for x in outcomes),"database_writes":False,"qdrant_writes":False}); emit("stage12_4b1_final_summary.json",manifest); print(json.dumps(manifest,indent=2,default=str))
if __name__=="__main__": main()
