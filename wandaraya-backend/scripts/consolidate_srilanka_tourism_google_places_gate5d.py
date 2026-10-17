"""Offline-only consolidation of completed Gate 5D live batch manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.time_context.governance.google_places_reconciliation import consolidate_manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="data/reports/stage_10_1_3e_gate5c_all_batches_v2_gate5c_v2_google_places_enrichment_queue.json")
    parser.add_argument("--manifests", nargs="+", required=True, help="one or more saved Gate 5D full-enrichment manifests")
    parser.add_argument("--previous-consolidation", help="Optional earlier offline consolidation to preserve while adding a new live batch.")
    parser.add_argument("--batch-id", default="consolidated")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    queue_path = Path(args.queue); queue = json.loads(queue_path.read_text(encoding="utf-8")).get("records", [])
    manifest_paths = [Path(value) for value in args.manifests]
    missing = [str(path) for path in manifest_paths if not path.is_file()]
    if missing: raise FileNotFoundError("manifest(s) not found: " + ", ".join(missing))
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in manifest_paths]
    source_manifests = [str(path) for path in manifest_paths]
    if args.previous_consolidation:
        previous_path = Path(args.previous_consolidation)
        if not previous_path.is_file():
            raise FileNotFoundError(f"previous consolidation not found: {previous_path}")
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        if previous.get("mode") != "offline_consolidation":
            raise ValueError("--previous-consolidation must be an offline consolidation report")
        # consolidate_manifests deliberately accepts saved live records only;
        # wrap prior immutable results so they remain part of the new checkpoint.
        manifests.insert(0, {"mode": "live", "results": previous.get("results", [])})
        source_manifests.insert(0, str(previous_path))
    result = consolidate_manifests(queue=queue, manifests=manifests)
    result["source_manifests"] = source_manifests
    output = Path(args.reports_dir) / f"stage_10_1_3e_gate5d_{args.batch_id}_google_places_consolidation.json"
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "network_requests": 0, "completed": len(result["completed_records"]), "remaining": len(result["remaining_records"]), "retriable": len(result["retriable_records"]), "report": str(output)}, indent=2))


if __name__ == "__main__": main()
