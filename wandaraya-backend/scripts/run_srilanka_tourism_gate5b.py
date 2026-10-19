"""Validate or execute a separately approved Gate 5B pilot."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from app.time_context.governance.live_pilot import StagedTourismChange, load_source_authorization_configuration
from app.time_context.governance.multi_page_pilot import Gate5BPilotPlan, execute_approved_pilot, extract_review_record, load_manifest_candidates, write_gate5b_reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-config", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--manifest", default="data/reports/stage_10_1_3e_gate5a_acquisition_manifest.json")
    parser.add_argument("--extract-html", help="Saved HTML file for offline extraction; makes no request.")
    parser.add_argument("--captured-url", help="Exact canonical URL for --extract-html.")
    parser.add_argument("--retrieved-at", help="Original timezone-aware retrieval timestamp for --extract-html.")
    parser.add_argument("--batch-id", help="Unique immutable identifier for a live capture/report batch.")
    parser.add_argument("--capture-root", default="data/review/srilanka_tourism", help="Review-only HTML fixture root for live capture.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()
    authorization = load_source_authorization_configuration(Path(args.authorization_config))
    try:
        plan = Gate5BPilotPlan.model_validate(json.loads(Path(args.plan).read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as error:
        parser.error(f"invalid Gate 5B plan: {error}")
    manifest = load_manifest_candidates(Path(args.manifest))
    errors = plan.readiness_errors(set(manifest))
    if args.extract_html:
        if not args.captured_url:
            parser.error("--extract-html requires --captured-url")
        candidate = manifest.get(args.captured_url)
        if candidate is None:
            parser.error("--captured-url must be an exact canonical URL from the Gate 5A manifest")
        content = Path(args.extract_html).read_bytes()
        retrieved_at = datetime.fromisoformat(args.retrieved_at) if args.retrieved_at else None
        if retrieved_at is not None and retrieved_at.tzinfo is None:
            parser.error("--retrieved-at must include a timezone offset")
        fetched = StagedTourismChange(source_url=args.captured_url, content_sha256=sha256(content).hexdigest(), raw_content=content,
                                      retrieved_at=retrieved_at, content_type="text/html; offline-capture", fetch_success=True)
        record = extract_review_record(fetched=fetched, candidate=candidate, authorization_reference=plan.approval_reference)
        reports = write_gate5b_reports(records=[record], plan=plan, reports_dir=Path("data/reports"), batch_id=args.batch_id)
        print(json.dumps({"mode": "offline_captured_html_extraction", "network_requests": 0, "record": record.model_dump(),
                          "reports": {name: str(path) for name, path in reports.items()}}, indent=2, default=str))
        return
    if not args.execute:
        print(json.dumps({"mode": "offline_plan_validation", "errors": errors, "approved_urls": [item.model_dump() for item in plan.approved_urls], "network_requests": 0}, indent=2, default=str))
        return
    if not args.confirm_execute:
        parser.error("--execute requires --confirm-execute")
    if not args.batch_id:
        parser.error("--execute requires a unique --batch-id to preserve captured HTML and prior reports")
    records = asyncio.run(execute_approved_pilot(authorization=authorization, plan=plan, manifest=manifest,
        capture_root=Path(args.capture_root), batch_id=args.batch_id))
    reports = write_gate5b_reports(records=records, plan=plan, reports_dir=Path("data/reports"), batch_id=args.batch_id)
    print(json.dumps({"mode": "gate5b_live_pilot", "records": [item.model_dump() for item in records], "reports": {name: str(path) for name, path in reports.items()}}, indent=2, default=str))


if __name__ == "__main__":
    main()
