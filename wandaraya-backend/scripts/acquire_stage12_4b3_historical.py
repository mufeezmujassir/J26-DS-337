"""Bounded 2010-2025 NASA POWER Batch 0/1 acquisition; no database writes."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import date
from pathlib import Path
from app.climate.providers.nasa_power import NasaPowerRequest, fetch, normalize
from app.climate.validation import validate_daily_records

ROOT=Path("data/climate"); REPORT=Path("data/reports"); START=date(2010,1,1); END=date(2025,12,31)
SELECTED={1:"coastal_geographic_distinction",24:"highland_elevation_distinction",16:"dry_zone_geographic_distinction"}
def write(path,content):
 path.parent.mkdir(parents=True,exist_ok=True)
 digest=hashlib.sha256(content).hexdigest()
 if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise RuntimeError(f"checksum-changing overwrite refused: {path}")
 if not path.exists(): path.write_bytes(content)
 return digest
def main():
 p=argparse.ArgumentParser(); p.add_argument("--dry-run",action="store_true"); p.add_argument("--resume",action="store_true"); p.add_argument("--max-locations",type=int,default=3); p.add_argument("--no-db-write",action="store_true"); args=p.parse_args()
 prior=json.loads((REPORT/"stage12_4b_pilot_locations.json").read_text())["locations"]; locations=[x for x in prior if x["id"] in SELECTED][:args.max_locations]
 if args.max_locations>3: raise SystemExit("bounded historical pilot maximum is three locations")
 manifest={"provider":"NASA POWER","dataset_version":"nasa_power_daily_v2.10.0_historical_2010_2025_batch01","period":{"start":str(START),"end":str(END),"expected_dates":5844},"time_standard":"UTC","download_status":"DRY_RUN" if args.dry_run else "PENDING","samples":[]}
 if args.dry_run:
  for x in locations: manifest["samples"].append({"sample_id":f"historic_{x['id']}","attraction_id":x["id"],"name":x["name"],"selection_method":SELECTED[x["id"]],"request_url":NasaPowerRequest(x["latitude"],x["longitude"],START,END).url(),"expected_dates":5844,"download_status":"NOT_REQUESTED"})
 else:
  for x in locations:
   name=f"nasa_power_historical_{x['id']}_{START:%Y%m%d}_{END:%Y%m%d}.json"; raw_path=ROOT/"raw/nasa_power/historical_2010_2025"/name
   try:
    if raw_path.exists(): raw=raw_path.read_bytes(); payload=json.loads(raw)
    else: payload,raw=fetch(NasaPowerRequest(x["latitude"],x["longitude"],START,END))
    checksum=write(raw_path,raw); records,meta=normalize(payload); validation=validate_daily_records(records, expected_records=5844)
    processed=json.dumps({"location":x,"records":records,"metadata":meta},sort_keys=True,indent=2).encode(); write(ROOT/"processed/nasa_power/historical_2010_2025"/name,processed)
    manifest["samples"].append({"sample_id":f"historic_{x['id']}","attraction_id":x["id"],"name":x["name"],"selection_method":SELECTED[x["id"]],"request_url":NasaPowerRequest(x["latitude"],x["longitude"],START,END).url(),"raw_file":str(raw_path),"checksum_sha256":checksum,"expected_dates":5844,"received_dates":validation["received"],"accepted_dates":validation["accepted"],"validation":validation,"metadata":meta,"download_status":"VALIDATED"})
   except Exception as exc: manifest["samples"].append({"attraction_id":x["id"],"status":"FAILED","error":str(exc)}); break
 manifest["download_status"]="VALIDATED" if len(manifest["samples"])==len(locations) and all(x.get("download_status")=="VALIDATED" for x in manifest["samples"]) else manifest["download_status"]
 blob=json.dumps(manifest,sort_keys=True,default=str).encode(); manifest["manifest_sha256"]=hashlib.sha256(blob).hexdigest(); write(ROOT/"manifests/nasa_power/historical_2010_2025/batch01_live_manifest_v3.json" if not args.dry_run else ROOT/"manifests/nasa_power/historical_2010_2025/batch01_dry_run_manifest.json",json.dumps(manifest,indent=2,default=str).encode())
 REPORT.mkdir(parents=True,exist_ok=True); (REPORT/"stage12_4b3_historical_manifest.json").write_text(json.dumps(manifest,indent=2,default=str)); (REPORT/"stage12_4b3_batch0_acquisition.json").write_text(json.dumps(manifest["samples"][:1],indent=2,default=str)); (REPORT/"stage12_4b3_batch1_acquisition.json").write_text(json.dumps(manifest["samples"][1:],indent=2,default=str)); print(json.dumps(manifest,indent=2,default=str))
if __name__=="__main__":main()
