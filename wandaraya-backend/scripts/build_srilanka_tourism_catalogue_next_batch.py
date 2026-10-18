"""Create a review-only next-batch plan from a consolidated Gate 5B.3 manifest."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from app.time_context.governance.catalogue_discovery import parse_researcher_approval_timestamp, validate_approval_reference, write_next_batch_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-manifest", required=True)
    parser.add_argument("--output-plan", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--approval-reference")
    parser.add_argument("--researcher-execution-approved-at", help="Timezone-aware ISO-8601 timestamp; omit for review-only plan.")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    source = Path(args.discovery_manifest)
    if not source.is_file():
        parser.error(f"discovery manifest was not found: {source}")
    raw = source.read_bytes()
    approved_at = None
    if args.researcher_execution_approved_at:
        try:
            approved_at = parse_researcher_approval_timestamp(args.researcher_execution_approved_at)
        except ValueError as error:
            parser.error(str(error))
    if args.approval_reference:
        try:
            args.approval_reference = validate_approval_reference(args.approval_reference)
        except ValueError as error:
            parser.error(str(error))
    plan = write_next_batch_plan(discovery_manifest=json.loads(raw), output_path=Path(args.output_plan), batch_id=args.batch_id,
                                 source_manifest_path=str(source), source_manifest_sha256=sha256(raw).hexdigest(),
                                 approval_reference=args.approval_reference, researcher_execution_approved_at=approved_at, batch_size=args.batch_size)
    print(json.dumps({"mode": "offline_next_batch_plan", "network_requests": 0, "output_plan": args.output_plan,
                      "candidate_count": len(plan["approved_urls"]), "approval_required": not bool(args.approval_reference and approved_at),
                      "source_manifest": str(source)}, indent=2))


if __name__ == "__main__":
    main()
