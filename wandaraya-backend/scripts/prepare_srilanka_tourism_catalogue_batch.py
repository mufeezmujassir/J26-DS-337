"""Prepare an auditable Gate 5B.3 plan and matching exact-URL authorization config.

This command is offline-only. It never makes a request and does not modify the
base authorization configuration supplied by the researcher.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from app.time_context.governance.catalogue_discovery import CatalogueBatchPlan, parse_researcher_approval_timestamp, validate_approval_reference, write_next_batch_plan
from app.time_context.governance.live_pilot import LivePilotSettings, load_source_authorization_configuration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-config", required=True)
    parser.add_argument("--discovery-manifest", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-plan", required=True)
    parser.add_argument("--output-authorization-config", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--researcher-execution-approved-at", required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    manifest_path = Path(args.discovery_manifest)
    raw = manifest_path.read_bytes()
    try:
        approved_at = parse_researcher_approval_timestamp(args.researcher_execution_approved_at)
        approval_reference = validate_approval_reference(args.approval_reference)
    except ValueError as error:
        parser.error(str(error))
    plan_data = write_next_batch_plan(discovery_manifest=json.loads(raw), output_path=Path(args.output_plan), batch_id=args.batch_id,
        source_manifest_path=str(manifest_path), source_manifest_sha256=sha256(raw).hexdigest(), approval_reference=approval_reference,
        researcher_execution_approved_at=approved_at, batch_size=args.batch_size)
    authorization = load_source_authorization_configuration(Path(args.authorization_config))
    # The base configuration remains untouched.  A live request is limited to
    # ten exact URLs, so this batch-scoped copy contains the selected URLs only;
    # all domains, conditions and rate-limit controls are preserved.
    merged = authorization.model_copy(update={"exact_urls": plan_data["exact_urls"]})
    Path(args.output_authorization_config).write_text(json.dumps(merged.model_dump(mode="json"), indent=2), encoding="utf-8")
    plan = CatalogueBatchPlan.model_validate(plan_data)
    allowed = set(json.loads(raw).get("remaining_urls", []))
    errors = plan.readiness_errors(allowed, LivePilotSettings().max_pages) + merged.readiness_errors(LivePilotSettings())
    errors += [f"exact_url_not_in_authorization_config:{url}" for url in sorted(set(plan.exact_urls) - set(merged.exact_urls))]
    print(json.dumps({"mode": "offline_batch_preparation", "network_requests": 0, "batch_id": args.batch_id,
                      "source_manifest": str(manifest_path), "source_manifest_sha256": sha256(raw).hexdigest(),
                      "plan": args.output_plan, "authorization_config": args.output_authorization_config,
                      "urls": plan_data["exact_urls"], "errors": sorted(set(errors))}, indent=2))


if __name__ == "__main__":
    main()
