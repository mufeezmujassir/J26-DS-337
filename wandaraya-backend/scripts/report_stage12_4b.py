"""Generate Stage 12.4B authorization-boundary reports without source downloads or DB writes."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("data/reports")
PILOT=ROOT / "stage12_4a_pilot_attractions.json"

def dump(name, value):
    ROOT.mkdir(parents=True, exist_ok=True); (ROOT/name).write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")

def main():
    now=datetime.now(timezone.utc).isoformat(); audit=json.loads(PILOT.read_text(encoding="utf-8"))
    wanted=[1,29,24,14,16,25]  # actual IDs: southwest, eastern, highland, dry-zone and wildlife coverage
    records={x["id"]:x for x in audit["attractions"]}; samples=[]
    for attraction_id in wanted:
        item=records[attraction_id].copy(); item.update({"sample_id":f"pilot_{attraction_id}", "proposed_climate_zone":"UNVERIFIED_RESEARCH_LABEL", "climate_zone_evidence_status":"NOT_YET_VALIDATED", "grid_cell_identification_method":"provider-returned coordinate / nearest eligible cell after approved acquisition"}); samples.append(item)
    source={"generated_at_utc":now,"status":"SOURCE_REVIEW_BLOCKED","provider":"Open-Meteo","underlying_dataset_requested":"ERA5-Land","endpoint":"https://archive-api.open-meteo.com/v1/archive","documentation":"https://open-meteo.com/en/docs/historical-weather-api","license_review":{"status":"BLOCKED","reason":"Open-Meteo pricing documentation states historical APIs require a Professional plan; this stage has no paid-tier authorization."},"no_request_made":True,"no_secrets_used":True}
    manifest={"status":"PILOT_ACQUISITION_BLOCKED","reason":"No authorized non-paid historical provider path was verified.","planned_period":{"start":"2024-01-01","end":"2024-12-31"},"planned_locations":samples,"variables":{"daily_precipitation_sum":"mm","daily_temperature_2m_mean":"C","daily_temperature_2m_min":"C","daily_temperature_2m_max":"C","optional":["relative_humidity_2m_mean (%)","wind_speed_10m_mean (km/h)","shortwave_radiation_sum (MJ/m²)"]},"limits":{"max_locations":8,"planned_locations":len(samples),"max_requests":8},"raw_storage":"data/climate/raw/open_meteo_era5_land/","processed_storage":"data/climate/processed/open_meteo_era5_land/","checksum_algorithm":"sha256"}
    schema={"status":"CLIMATE_STORAGE_IMPLEMENTED_AWAITING_APPROVAL","models":"app/models/climate.py","migration":"migrations/versions/e67f8a9b0c1d_add_versioned_climate_tables.py","migration_applied":False,"existing_weather_tables_modified":False,"review_command":"docker exec -it wandaraya-api-cutover alembic upgrade e67f8a9b0c1d"}
    mapping={"status":"PREVIEW_ONLY","records": [{"attraction_id":x["id"],"mapping_method":"PROVIDER_GRID_PENDING_ACQUISITION","distance_km":None,"confidence":"UNAVAILABLE_UNTIL_GRID_COORDINATE_RETURNED"} for x in samples],"risks":["central-highland elevation gradients","coastal microclimates","grid resolution/interpolation uncertainty"]}
    empty={"status":"NOT_RUN","reason":"Source review blocks acquisition; no fabricated climate observations.","postgresql_writes":False,"qdrant_writes":False}
    reports={"stage12_4b_source_verification.json":source,"stage12_4b_pilot_locations.json":{"generated_at_utc":now,"count":len(samples),"locations":samples},"stage12_4b_acquisition_manifest.json":manifest,"stage12_4b_raw_data_validation.json":empty,"stage12_4b_climate_quality_report.json":empty,"stage12_4b_schema_verification.json":schema,"stage12_4b_attraction_mapping_preview.json":mapping,"stage12_4b_existing_weather_comparison.json":empty,"stage12_4b_ingestion_dry_run.json":empty,"stage12_4b_regression_tests.json":{"status":"PENDING_TEST_EXECUTION","real_data_used":False}}
    for name,payload in reports.items(): dump(name,payload)
    final={"generated_at_utc":now,"status":"SOURCE_REVIEW_BLOCKED","reason":"Historical Open-Meteo access is documented as Professional-plan-only and no paid access is authorized.","pilot_locations":len(samples),"actual_records_downloaded":0,"postgresql_live_writes":False,"qdrant_writes":False,"production_ranking_changed":False,"migration_applied":False,"next_authorization":"Approve a provider and its usage terms (and, if Open-Meteo is chosen, a paid Professional plan) before acquisition; separately approve migration before persistence."}
    dump("stage12_4b_final_summary.json",final)
    doc=Path("docs/research/STAGE_12_4B_HISTORICAL_CLIMATE_ACQUISITION.md"); doc.parent.mkdir(parents=True,exist_ok=True)
    doc.write_text("# Stage 12.4B — Historical Climate Acquisition\n\nStatus: `SOURCE_REVIEW_BLOCKED`.\n\nOpen-Meteo documentation identifies ERA5-Land as a selectable historical reanalysis model, but its pricing documentation says historical APIs require a Professional plan. No paid access was authorized, so this stage made no API request and wrote no climate observations. The six real attraction-linked pilot locations, schema proposal and request manifest are recorded in the Stage 12.4B reports.\n\nThe migration is generated for review only and has not been applied.\n",encoding="utf-8")
    print(json.dumps(final,indent=2))
if __name__ == "__main__": main()
