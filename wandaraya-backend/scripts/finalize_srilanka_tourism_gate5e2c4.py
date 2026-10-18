"""Gate 5E.2C.4 final read-only write-authorization preflight.

No DML, Qdrant operation, or provider request is implemented here.  It creates
the immutable 24-record scope a future separately authorised transaction must
match exactly.
"""
from __future__ import annotations

import argparse, asyncio, json
from pathlib import Path
from typing import Any

from scripts.sync_srilanka_tourism_gate5e2c3 import B1, B6, BASE, db_snapshot, digest, file_digest, resolve_and_audit, validate_manifest, write_json


def build_reports(*, approved: list[dict[str, Any]], enriched: list[dict[str, Any]], upstream: list[dict[str, Any]], validation: dict[str, Any], prior: dict[str, dict[str, Any]], snapshot: dict[str, Any], batch_id: str, manifest_sha: str) -> dict[str, Any]:
    valid, invalid = validate_manifest(approved=approved, enriched=enriched, upstream=upstream, validation=validation)
    payloads, audit = resolve_and_audit(valid=valid, prior=prior, snapshot=snapshot, batch_id=batch_id)
    conflicts = [row for row in audit if row["classification"] != "NEW_INSERT_READY"]
    scope = {"source_provider": "srilanka_tourism", "source_approval_manifest_sha256": manifest_sha, "records": sorted(payloads, key=lambda x: x["source_attraction_id"]), "writes_executed": False}
    scope_hash = digest(scope)
    plan = {"operation": "atomic_insert_scope", "scope_sha256": scope_hash, "records": [{"source_attraction_id": row["source_attraction_id"], "operations": ["insert_attraction", "insert_primary_category", "insert_source_reference", "insert_field_provenance"]} for row in scope["records"]], "transaction_rules": ["fresh_recheck_inside_transaction", "unique_google_place_id", "unique_source_provider_external_source_id", "rollback_entire_scope_on_error", "no_qdrant_write"], "writes_executed": False}
    plan_hash = digest(plan)
    blocked_ids = sorted({row.get("source_attraction_id") for row in validation.get("blocked", []) if row.get("source_attraction_id")})
    return {
        "final_write_scope_manifest": {**scope, "write_scope_sha256": scope_hash},
        "identity_conflict_details": {"records": conflicts},
        "precommit_database_validation": {"valid_approved_actions": len(valid), "invalid_approved_actions": invalid, "ready_actions": len(payloads), "conflicts": conflicts, "active_attraction_count": len(snapshot["attractions"]), "writes_executed": False},
        "transaction_safety_validation": {"atomic_scope": True, "rollback_required_on_any_error": True, "fresh_collision_recheck_required": True, "idempotency_key": "source_provider + external_source_id", "qdrant_writes_executed": False},
        "write_scope_integrity": {"source_manifest_sha256": manifest_sha, "write_scope_sha256": scope_hash, "record_count": len(payloads), "excluded_conflict_ids": [row["source_attraction_id"] for row in conflicts], "excluded_prior_blocked_ids": blocked_ids},
        "final_execution_plan": {**plan, "execution_plan_sha256": plan_hash},
        "authorization_requirements": {"required": ["--execute", "--confirm-execute", f"--manifest-sha256 {manifest_sha}", f"--write-scope-sha256 {scope_hash}", f"--execution-plan-sha256 {plan_hash}", "explicit 24-record human-approved scope", "fresh in-transaction collision recheck"], "transaction_execution_enabled": False},
        "summary": {"ready_insertions": len(payloads), "identity_conflicts": len(conflicts), "conflicting_source_attraction_ids": [row["source_attraction_id"] for row in conflicts], "ready_source_attraction_ids": [row["source_attraction_id"] for row in scope["records"]], "existing_active_attraction_count": len(snapshot["attractions"]), "estimated_active_attraction_count_after": len(snapshot["attractions"]) + len(payloads), "write_scope_sha256": scope_hash, "final_execution_plan_sha256": plan_hash, "postgresql_writes_executed": False, "qdrant_writes_executed": False, "external_api_requests": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--manifest", default=BASE + "reapproved_action_manifest.json")
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.add_argument("--execute", action="store_true"); parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--manifest-sha256"); parser.add_argument("--write-scope-sha256"); parser.add_argument("--execution-plan-sha256")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    if args.execute or args.confirm_execute: parser.error("C.4 transaction execution is not enabled in this read-only stage.")
    manifest_path = Path(args.manifest); manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enriched = json.loads(Path(BASE + "metadata_enrichment_manifest.json").read_text(encoding="utf-8"))["records"]
    upstream = json.loads(Path(B6).read_text(encoding="utf-8"))["records"]
    validation = json.loads(Path(BASE + "reapproval_validation.json").read_text(encoding="utf-8"))
    prior = {x["external_source_id"]: x for x in json.loads(Path(B1).read_text(encoding="utf-8"))["records"]}
    reports = build_reports(approved=manifest["records"], enriched=enriched, upstream=upstream, validation=validation, prior=prior, snapshot=asyncio.run(db_snapshot()), batch_id=args.batch_id, manifest_sha=file_digest(manifest_path))
    prefix = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2c4_{args.batch_id}_"; paths = {}
    for name, value in reports.items():
        path = prefix.with_name(prefix.name + name + ".json"); write_json(path, value); paths[name] = str(path)
    print(json.dumps({"mode": "final_read_only_authorization_preflight", "summary": reports["summary"], "reports": paths}, indent=2))

if __name__ == "__main__": main()
