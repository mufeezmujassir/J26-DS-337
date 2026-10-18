"""Generate review-only exact-URL batches from captured official listing records."""
from __future__ import annotations

import json
from pathlib import Path

from app.time_context.governance.detail_batch_planning import build_detail_manifest_from_listing, write_detail_batches


def main() -> None:
    reports = Path("data/reports")
    manifest = build_detail_manifest_from_listing(reports / "stage_10_1_3e_gate5b_extraction_results.json")
    manifest_path = reports / "stage_10_1_3e_gate5b1_detail_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    batches = write_detail_batches(manifest=manifest, reports_dir=reports)
    print(json.dumps({"mode": "offline_review_only", "detail_urls": manifest["candidate_count"],
                      "manifest": str(manifest_path), "batches": [str(path) for path in batches], "network_requests": 0}, indent=2))


if __name__ == "__main__":
    main()
