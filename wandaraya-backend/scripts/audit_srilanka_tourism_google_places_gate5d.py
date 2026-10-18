"""Reclassify saved Gate 5D candidates offline after matching-rule improvements."""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
from app.time_context.governance.catalogue_reconciliation import load_existing_attractions
from app.time_context.governance.google_places_reconciliation import Gate5DSettings, classify_result, write_gate5d_reports

def raw_candidate(item):
    return {"id": item.get("google_place_id"), "displayName": item.get("display_name"), "formattedAddress": item.get("formatted_address"),
            "location": item.get("coordinates") or {}, "types": item.get("types") or [], "primaryType": item.get("primary_type"),
            "googleMapsUri": item.get("google_maps_uri"), "businessStatus": item.get("business_status")}

async def run(args):
    queue_path, manifest_path = Path(args.queue), Path(args.manifest)
    queue = json.loads(queue_path.read_text(encoding="utf-8")).get("records", [])
    records = {str(item.get("external_source_id")): item for item in queue}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing = await load_existing_attractions(); results = []
    for previous in manifest.get("results", []):
        record = records.get(str(previous.get("external_source_id")), {"external_source_id": previous.get("external_source_id"), "attraction_name": previous.get("attraction_name"), "source_url": previous.get("source_url")})
        results.append(classify_result(record, [raw_candidate(item) for item in previous.get("candidates", [])], existing, Gate5DSettings(), error=previous.get("error")))
    usage = {"mode": "offline_revalidation", "network_requests": 0, "selected_records": len(results), "search_requests": 0, "details_requests": 0, "max_records": len(results), "max_candidates": 0, "request_interval_seconds": 0, "max_retries": 0}
    paths = write_gate5d_reports(results=results, usage=usage, queue_path=queue_path, reports_dir=Path(args.reports_dir), batch_id=args.batch_id)
    return {"mode": "offline_revalidation", "network_requests": 0, "postgresql_writes": False, "qdrant_writes": False, "reports": {k:str(v) for k,v in paths.items()}}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest", required=True); p.add_argument("--queue", default="data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json"); p.add_argument("--batch-id", default="pilot_01_revalidated"); p.add_argument("--reports-dir", default="data/reports")
    print(json.dumps(asyncio.run(run(p.parse_args())), indent=2))
if __name__ == "__main__": main()
