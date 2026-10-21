"""Prepare (never acquire) the remaining district-coordinate historical samples."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from app.climate.providers.nasa_power import NasaPowerRequest

R=Path('data/reports'); OUT=Path('data/climate/manifests/nasa_power/historical_2010_2025')
def main():
 plan=json.loads((R/'stage12_4b2_historical_sampling_plan.json').read_text())['district_samples']
 batch01=json.loads((R/'stage12_4b3_historical_manifest.json').read_text())['samples']
 acquired={(round(json.loads(Path(x['raw_file'].replace('raw/nasa_power/','processed/nasa_power/')).read_text())['location']['latitude'],7),round(json.loads(Path(x['raw_file'].replace('raw/nasa_power/','processed/nasa_power/')).read_text())['location']['longitude'],7)) for x in batch01}
 reconciled=[]
 for d in plan:
  key=(round(d['latitude'],7),round(d['longitude'],7)); same=key in acquired
  reconciled.append({"district_id":d['id'],"district_name":d['name'],"representative_coordinate":{"latitude":d['latitude'],"longitude":d['longitude']},"matches_batch01_coordinate":same,"reason":"exact_coordinate_match" if same else "Batch01 used attraction coordinate; it does not satisfy this district representative coordinate."})
 remaining=[x for x in reconciled if not x['matches_batch01_coordinate']]
 samples=[]
 for x in remaining:
  lat=x['representative_coordinate']['latitude'];lon=x['representative_coordinate']['longitude'];did=x['district_id']
  samples.append({"sample_id":f"district_{did}_representative_2010_2025","district_id":did,"district_name":x['district_name'],"province":next(d['province'] for d in plan if d['id']==did),"latitude":lat,"longitude":lon,"selection_method":"existing_district_representative_coordinate","spatial_uncertainty":"COARSE_GRID_REPRESENTATIVE_ONLY","provider":"NASA POWER","source_products":"to be recorded from response","date_range":"2010-01-01..2025-12-31","time_standard":"UTC","parameters":["T2M","T2M_MAX","T2M_MIN","PRECTOTCORR","RH2M","WS10M","ALLSKY_SFC_SW_DWN"],"expected_records":5844,"request_url":NasaPowerRequest(lat,lon,date(2010,1,1),date(2025,12,31)).url(),"raw_file":f"data/climate/raw/nasa_power/historical_2010_2025/district_{did}_20100101_20251231.json","processed_file":f"data/climate/processed/nasa_power/historical_2010_2025/district_{did}_20100101_20251231.json","download_status":"NOT_AUTHORIZED","checksum_status":"NOT_AVAILABLE","persistence_status":"NOT_PERSISTED"})
 manifest={"dataset_version":"nasa_power_daily_v2.10.0_historical_2010_2025_batch02_proposed","provider":"NASA POWER","time_standard":"UTC","samples":samples,"expected_records":len(samples)*5844,"external_requests_issued":0}
 R.mkdir(parents=True,exist_ok=True);(R/'stage12_4b4_district_sample_reconciliation.json').write_text(json.dumps({"district_representatives":len(plan),"batch01_attraction_coordinates":len(batch01),"exact_matches":len(plan)-len(remaining),"remaining":len(remaining),"records":reconciled},indent=2));(R/'stage12_4b4_batch02_manifest.json').write_text(json.dumps(manifest,indent=2));OUT.mkdir(parents=True,exist_ok=True);(OUT/'batch02_proposed_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({"remaining":len(remaining),"expected_records":manifest['expected_records'],"external_requests":0},indent=2))
if __name__=='__main__':main()
