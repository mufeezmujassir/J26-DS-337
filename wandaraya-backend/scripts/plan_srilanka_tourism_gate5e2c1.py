"""Gate 5E.2C.1 integrity audit and PostgreSQL synchronization dry-run.

This command is intentionally read-only.  It audits human-approved actions and
emits proposed operations; it never calls ``commit`` and has no Qdrant client.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any


BASE = "data/reports/stage_10_1_3e_gate5e2b6_all_completed_v1_"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def audit_manifest(*, manifest: dict[str, Any], proposals: list[dict[str, Any]], validation: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    proposal_by_id = {item["source_attraction_id"]: item for item in proposals}
    validation_by_id = {item["source_attraction_id"]: item for item in validation.get("approved_actions", [])}
    records = manifest.get("records", [])
    ids = [item.get("source_attraction_id") for item in records]
    duplicates = sorted(source for source, count in Counter(ids).items() if count > 1)
    valid, invalid = [], []
    checkpoint_hash = _hash(checkpoint)
    for record in records:
        source = record.get("source_attraction_id"); proposal = proposal_by_id.get(source); approved = validation_by_id.get(source)
        reasons = []
        if not proposal: reasons.append("missing_final_proposal")
        elif record.get("final_proposal_sha256") != proposal.get("final_proposal_sha256"): reasons.append("stale_or_modified_proposal")
        if record.get("checkpoint_sha256") != checkpoint_hash: reasons.append("stale_checkpoint_hash")
        if not approved: reasons.append("not_present_in_reviewer_validation")
        elif approved.get("approved_action") != record.get("approved_action"): reasons.append("reviewer_action_mismatch")
        if not record.get("reviewer_identity") or not record.get("review_timestamp") or not record.get("review_notes"): reasons.append("incomplete_reviewer_evidence")
        (invalid if reasons else valid).append({"record": record, "reasons": reasons})
    return {"json_valid": True, "approved_record_count": len(records), "unique_source_attraction_ids": len(set(ids)), "duplicate_source_attraction_ids": duplicates, "checkpoint_sha256_valid": manifest.get("checkpoint_sha256") == checkpoint_hash, "valid_records": valid, "invalid_records": invalid}


def plan_operations(*, valid_records: list[dict[str, Any]], evidence: list[dict[str, Any]], duplicate_clusters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_by_id = {item["source_attraction_id"]: item for item in evidence}
    cluster_members = {source for cluster in duplicate_clusters.get("clusters", []) if cluster.get("resolution") != "RESOLVED" for source in cluster.get("source_attraction_ids", [])}
    planned, quarantined = [], []
    seen_place_ids: set[str] = set()
    for entry in valid_records:
        record = entry["record"]; source = record["source_attraction_id"]; item = evidence_by_id.get(source, {})
        action = record["approved_action"]; reasons = []
        if source in cluster_members: reasons.append("unresolved_duplicate_cluster")
        if action == "INSERT_NEW_CANDIDATE":
            # A new attraction needs source identity and concrete location metadata.
            if not item.get("official_attraction_identity"): reasons.append("missing_official_name")
            if not item.get("source_provenance", {}).get("official_source_url"): reasons.append("missing_source_url")
            candidate = item.get("google_candidate_identity")
            if not candidate: reasons.append("missing_google_place_id")
            if item.get("existing_kb_target_attraction_id"): reasons.append("existing_kb_duplicate_candidate")
            if candidate in seen_place_ids: reasons.append("duplicate_google_place_id_in_approved_manifest")
            # B.5 identity results carry coordinates but the approved action
            # payload does not yet contain verified official district/category.
            reasons.extend(["missing_verified_district", "missing_verified_category"])
            if candidate: seen_place_ids.add(candidate)
        elif action == "LINK_SOURCE_REFERENCE_CANDIDATE":
            if not item.get("existing_kb_target_attraction_id"): reasons.append("missing_valid_existing_target")
            if not item.get("source_provenance", {}).get("official_source_url"): reasons.append("missing_source_url")
        else:
            reasons.append("unsupported_approved_action")
        operation = {"source_attraction_id": source, "operation": "INSERT attraction and source reference" if action == "INSERT_NEW_CANDIDATE" else "LINK source reference", "approved_action": action, "target_attraction_id": item.get("existing_kb_target_attraction_id"), "google_place_id": item.get("google_candidate_identity"), "official_name": item.get("official_attraction_identity"), "source_url": item.get("source_provenance", {}).get("official_source_url"), "action_hash": record.get("final_proposal_sha256"), "reviewer_identity": record.get("reviewer_identity")}
        if reasons: quarantined.append({**operation, "quarantine_reasons": reasons})
        else: planned.append(operation)
    return planned, quarantined


async def active_attraction_count() -> int:
    from sqlalchemy import func, select
    from app.database import AsyncSessionLocal
    from app.models.attraction import Attraction
    async with AsyncSessionLocal() as session:
        return int((await session.scalar(select(func.count()).select_from(Attraction).where(Attraction.is_active.is_(True)))) or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=BASE + "approved_action_manifest.json")
    parser.add_argument("--proposals", default=BASE + "final_action_proposals.json")
    parser.add_argument("--validation", default=BASE + "reviewer_validation.json")
    parser.add_argument("--evidence", default=BASE + "final_identity_evidence.json")
    parser.add_argument("--duplicate-clusters", default=BASE + "duplicate_cluster_review.json")
    parser.add_argument("--checkpoint", default="data/reports/stage_10_1_3e_gate5e2b5_all_completed_v1_verification_checkpoint.json")
    parser.add_argument("--reports-dir", default="data/reports"); parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--execute", action="store_true", help="Reserved for a future explicitly-authorized executor; rejected here.")
    args = parser.parse_args()
    if args.execute: parser.error("Gate 5E.2C.1 is dry-run only; no PostgreSQL write executor is enabled.")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); proposals = json.loads(Path(args.proposals).read_text(encoding="utf-8")).get("records", [])
    validation = json.loads(Path(args.validation).read_text(encoding="utf-8")); evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")).get("records", [])
    clusters = json.loads(Path(args.duplicate_clusters).read_text(encoding="utf-8")); checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    integrity = audit_manifest(manifest=manifest, proposals=proposals, validation=validation, checkpoint=checkpoint)
    planned, quarantined = plan_operations(valid_records=integrity["valid_records"], evidence=evidence, duplicate_clusters=clusters)
    current_count = asyncio.run(active_attraction_count())
    planned_inserts = [item for item in planned if item["approved_action"] == "INSERT_NEW_CANDIDATE"]
    planned_links = [item for item in planned if item["approved_action"] == "LINK_SOURCE_REFERENCE_CANDIDATE"]
    preflight = {"status": "NOT_READY_FOR_WRITE" if quarantined or integrity["invalid_records"] else "READY_FOR_EXPLICITLY_AUTHORIZED_WRITE", "reasons": ["quarantined actions require renewed evidence or cluster resolution"] if quarantined else [], "dry_run": True, "postgresql_writes": False, "qdrant_writes": False}
    payloads = {"manifest_integrity_audit": integrity, "duplicate_action_audit": {"duplicate_source_attraction_ids": integrity["duplicate_source_attraction_ids"], "unresolved_clusters": clusters.get("clusters", [])}, "approved_action_validation": {"passing": len(integrity["valid_records"]), "failing": len(integrity["invalid_records"]), "records": integrity["invalid_records"]}, "quarantined_actions": {"records": quarantined}, "synchronization_plan": {"operations": planned, "dry_run": True}, "planned_insertions": {"records": planned_inserts}, "planned_source_links": {"records": planned_links}, "transaction_preflight": preflight, "expected_database_changes": {"active_attractions_before": current_count, "planned_attraction_inserts": len(planned_inserts), "planned_source_links": len(planned_links), "estimated_active_attractions_after": current_count + len(planned_inserts), "writes_executed": False}, "summary": {"unique_approved_source_ids": integrity["unique_source_attraction_ids"], "duplicate_approved_source_ids": len(integrity["duplicate_source_attraction_ids"]), "approved_actions_passing_manifest_validation": len(integrity["valid_records"]), "quarantined_actions": len(quarantined), "planned_insertions": len(planned_inserts), "planned_source_links": len(planned_links), "postgresql_writes": False, "qdrant_writes": False, "external_api_requests": 0}}
    prefix = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2c1_{args.batch_id}_"; paths = {}
    for key, value in payloads.items(): paths[key] = prefix.with_name(prefix.name + key + ".json"); _write(paths[key], value)
    print(json.dumps({"mode": "dry_run", "summary": payloads["summary"], "preflight": preflight, "reports": {key: str(path) for key, path in paths.items()}}, indent=2))


if __name__ == "__main__": main()
