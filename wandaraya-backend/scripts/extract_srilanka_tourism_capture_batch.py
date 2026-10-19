"""Re-extract one immutable Gate 5B HTML capture batch without network access."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from app.time_context.governance.live_pilot import StagedTourismChange
from app.time_context.governance.multi_page_pilot import (
    Gate5BPilotPlan,
    extract_review_record,
    load_manifest_candidates,
    write_gate5b_reports,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-manifest", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--manifest", default="data/reports/stage_10_1_3e_gate5b1_detail_manifest.json")
    parser.add_argument("--batch-id", required=True, help="New report-only identifier; capture files are never modified.")
    args = parser.parse_args()

    capture_manifest_path = Path(args.capture_manifest)
    capture = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
    plan = Gate5BPilotPlan.model_validate(json.loads(Path(args.plan).read_text(encoding="utf-8")))
    candidates = load_manifest_candidates(Path(args.manifest))
    records = []
    for artifact in capture.get("artifacts", []):
        url = artifact["source_url"]
        candidate = candidates.get(url)
        if candidate is None:
            raise ValueError(f"captured URL is absent from review manifest: {url}")
        content = (capture_manifest_path.parent / artifact["file"]).read_bytes()
        digest = sha256(content).hexdigest()
        if digest != artifact["content_sha256"]:
            raise ValueError(f"fixture checksum mismatch: {artifact['file']}")
        retrieved_at = datetime.fromisoformat(artifact["retrieved_at"])
        if retrieved_at.tzinfo is None:
            raise ValueError(f"fixture timestamp must be timezone-aware: {artifact['file']}")
        fetched = StagedTourismChange(
            source_url=url,
            content_sha256=digest,
            raw_content=content,
            http_status=artifact.get("http_status"),
            content_type=f"{artifact.get('content_type')}; offline-capture",
            response_size_bytes=artifact.get("response_size_bytes"),
            retrieved_at=retrieved_at,
            fetch_success=True,
        )
        records.append(extract_review_record(fetched=fetched, candidate=candidate, authorization_reference=plan.approval_reference))
    reports = write_gate5b_reports(records=records, plan=plan, reports_dir=Path("data/reports"), batch_id=args.batch_id)
    print(json.dumps({
        "mode": "offline_captured_batch_extraction",
        "network_requests": 0,
        "capture_batch_id": capture.get("batch_id"),
        "records": len(records),
        "reports": {name: str(path) for name, path in reports.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
