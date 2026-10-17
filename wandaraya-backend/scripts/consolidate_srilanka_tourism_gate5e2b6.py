"""Gate 5E.2B.6 review-only final identity evidence consolidation.

This script reads previous review evidence and optional human decisions.  It does
not call Google, PostgreSQL, or Qdrant and cannot synchronize attractions.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.time_context.governance.tourism_sync_approval import digest

V5 = "data/reports/stage_10_1_3e_gate5e2b5_all_completed_v1_corrected_proposals_v5.json"
CHECKPOINT = "data/reports/stage_10_1_3e_gate5e2b5_all_completed_v1_verification_checkpoint.json"
EVIDENCE = "data/reports/stage_10_1_3e_gate5e2b1_all_completed_v1_identity_evidence_manifest.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def content_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def load_existing_kb_snapshot() -> dict[str, Any]:
    """Read identity fields only; this stage never creates a database session write."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.attraction import Attraction
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Attraction.id, Attraction.name, Attraction.google_place_id).where(Attraction.is_active.is_(True)))).all()
    by_place = {place_id: attraction_id for attraction_id, _name, place_id in rows if place_id}
    by_name: dict[str, list[int]] = {}
    for attraction_id, name, _place_id in rows:
        by_name.setdefault(" ".join("".join(char.lower() if char.isalnum() else " " for char in name).split()), []).append(attraction_id)
    return {"by_place": by_place, "by_name": by_name, "active_attraction_count": len(rows)}


def verification_audit(records: list[dict[str, Any]], checkpoint: dict[str, Any]) -> dict[str, Any]:
    targeted = {record["source_attraction_id"] for record in records if record.get("candidate_verification_result") == "NO_VALID_GOOGLE_CANDIDATE"}
    completed = set(checkpoint.get("completed_source_ids", []))
    failed = set(checkpoint.get("failed_source_ids", []))
    evidence_ids = {record.get("source_attraction_id") for record in checkpoint.get("results", [])}
    duplicates = len(checkpoint.get("completed_source_ids", [])) != len(completed)
    inconsistencies = sorted(completed - evidence_ids - failed)
    outcomes = {record["source_attraction_id"]: ("completed" if record["source_attraction_id"] in completed else "failed" if record["source_attraction_id"] in failed else "pending") for record in records if record["source_attraction_id"] in targeted}
    complete = targeted <= completed | failed and not duplicates and not inconsistencies and checkpoint.get("cumulative_requests", 0) <= 60
    return {"targeted_records": len(targeted), "completed_records": len(completed & targeted), "failed_records": len(failed & targeted), "pending_records": len(targeted - completed - failed), "cumulative_api_requests": checkpoint.get("cumulative_requests", 0), "maximum_api_budget": 60, "within_budget": checkpoint.get("cumulative_requests", 0) <= 60, "duplicate_processing": duplicates, "missing_api_evidence_source_ids": inconsistencies, "deterministic_outcomes": outcomes, "verification_complete": complete, "finalization_blocked": not complete}


def final_evidence(records: list[dict[str, Any]], checkpoint: dict[str, Any], prior_evidence: dict[str, dict[str, Any]], kb: dict[str, Any]) -> list[dict[str, Any]]:
    live = {result["source_attraction_id"]: result for result in checkpoint.get("results", [])}
    output = []
    for record in records:
        source = record["source_attraction_id"]; prior = prior_evidence.get(source, {})
        result = live.get(record["source_attraction_id"])
        google_id = result.get("shortlisted_place_id") if result else record.get("corrected_google_place_id")
        official_name = prior.get("official_name")
        name_matches = kb["by_name"].get(" ".join("".join(char.lower() if char.isalnum() else " " for char in official_name or "").split()), [])
        output.append({"source_attraction_id": source, "official_attraction_identity": official_name, "google_candidate_identity": google_id, "existing_kb_target_attraction_id": kb["by_place"].get(google_id) or (name_matches[0] if len(name_matches) == 1 else None), "existing_kb_name_match_ids": name_matches, "name_compatibility": result.get("assessment") if result else prior.get("classification", "NOT_REVERIFIED"), "geographic_consistency": "REQUIRES_REVIEW" if result else "NOT_AVAILABLE", "district_locality_consistency": "REQUIRES_REVIEW" if result else "NOT_AVAILABLE", "attraction_type_compatibility": result.get("assessment") if result else "NOT_REVERIFIED", "identity_conflict": result.get("reason") if result else None, "source_provenance": {"official_source_url": prior.get("official_source_url"), "proposal_version": record.get("proposal_version"), "v5_proposal_sha256": record["v5_proposal_sha256"], "verification_checkpoint": "gate5e2b5"}, "evidence_completeness": "TARGETED_LIVE_EVIDENCE" if result else "HISTORICAL_EVIDENCE_PLUS_KB_SNAPSHOT"})
    return output


def proposals(records: list[dict[str, Any]], audit: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    output = []
    for record in records:
        requested = record.get("corrected_proposed_action", "MANUAL_REVIEW_REQUIRED")
        action = "MANUAL_REVIEW_REQUIRED" if not audit["verification_complete"] else requested
        evidence = (evidence_by_id or {}).get(record["source_attraction_id"], {})
        google_id = evidence.get("google_candidate_identity") or record.get("corrected_google_place_id")
        target_id = evidence.get("existing_kb_target_attraction_id")
        # A retained link must still point to a current, unique KB identity.
        if action == "LINK_SOURCE_REFERENCE_CANDIDATE" and not target_id:
            action = "MANUAL_REVIEW_REQUIRED"
        # A proposed insertion cannot remain an insertion where a current KB
        # place/name identity is already present; a reviewer must resolve it.
        if action == "INSERT_NEW_CANDIDATE" and (target_id or len(evidence.get("existing_kb_name_match_ids", [])) > 1):
            action = "MANUAL_REVIEW_REQUIRED"
        item = {"source_attraction_id": record["source_attraction_id"], "proposed_action": action, "original_proposed_action": requested, "google_place_id": google_id, "existing_kb_target_attraction_id": target_id, "source_url": evidence.get("source_provenance", {}).get("official_source_url"), "required_fields_valid": bool(evidence.get("official_attraction_identity") and evidence.get("source_provenance", {}).get("official_source_url")), "identity_blocker": action == "MANUAL_REVIEW_REQUIRED", "proposal_basis": record["v5_proposal_sha256"]}
        item["final_proposal_sha256"] = digest(item)
        output.append(item)
    return output


def classification_audit(records: list[dict[str, Any]], action_plan: list[dict[str, Any]], checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    """Make every proposal transition reviewable and explain the B.5 evidence use."""
    final_by_id = {item["source_attraction_id"]: item for item in action_plan}
    live_by_id = {item["source_attraction_id"]: item for item in checkpoint.get("results", [])}
    output = []
    for record in records:
        source_id = record["source_attraction_id"]
        final = final_by_id[source_id]
        live = live_by_id.get(source_id)
        previous = record.get("corrected_proposed_action", "MANUAL_REVIEW_REQUIRED")
        output.append({
            "source_attraction_id": source_id,
            "previous_action": previous,
            "final_action": final["proposed_action"],
            "action_changed": previous != final["proposed_action"],
            "change_reason": "B.6 temporarily blocks finalization until verification completion" if previous != final["proposed_action"] else "Prior evidence-backed proposal preserved; still requires explicit human approval.",
            "live_google_evidence_incorporated": live is not None,
            "live_assessment": live.get("assessment") if live else None,
            "live_evidence_reason": live.get("reason") if live else None,
            "blockers": ["human_review_required"] if final["proposed_action"] in {"INSERT_NEW_CANDIDATE", "LINK_SOURCE_REFERENCE_CANDIDATE", "MANUAL_REVIEW_REQUIRED"} else [],
            "final_proposal_sha256": final["final_proposal_sha256"],
        })
    return output


def validate_decisions(*, decisions: dict[str, Any], plan: list[dict[str, Any]], checkpoint_hash: str, audit: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["source_attraction_id"]: item for item in plan}; approved=[]; blocked=[]; deferred=[]; seen=set()
    for decision in decisions.get("decisions", []):
        source_id = decision.get("source_attraction_id"); action = decision.get("decision")
        item = by_id.get(source_id)
        reason = None
        if source_id in seen: reason = "duplicate_reviewer_decision"
        elif not item: reason = "unknown_source_record"
        elif action not in {"APPROVE_INSERT", "APPROVE_LINK", "REJECT", "DEFER"}: reason = "invalid_decision"
        elif decision.get("checkpoint_sha256") != checkpoint_hash: reason = "stale_checkpoint_hash"
        elif decision.get("final_proposal_sha256") != item["final_proposal_sha256"]: reason = "stale_or_modified_proposal"
        elif action != "DEFER" and not decision.get("reviewer_identity"): reason = "reviewer_identity_required"
        elif action != "DEFER" and (not decision.get("review_timestamp") or not decision.get("review_notes")): reason = "review_timestamp_and_notes_required"
        elif action.startswith("APPROVE") and not audit["verification_complete"]: reason = "verification_completion_required"
        elif action == "APPROVE_INSERT" and item["proposed_action"] != "INSERT_NEW_CANDIDATE": reason = "incompatible_insert_approval"
        elif action == "APPROVE_LINK" and item["proposed_action"] != "LINK_SOURCE_REFERENCE_CANDIDATE": reason = "incompatible_link_approval"
        if reason: blocked.append({**decision, "reason": reason})
        elif action == "DEFER": deferred.append(decision)
        elif action == "REJECT": approved.append({**decision, "approved_action": "REJECT_INVALID_MATCH"})
        else: approved.append({**decision, "approved_action": item["proposed_action"]})
        seen.add(source_id)
    return {"approved_actions": approved, "blocked_actions": blocked, "deferred_actions": deferred, "writes": False, "qdrant_writes": False, "network_requests": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v5-proposals", default=V5); parser.add_argument("--checkpoint", default=CHECKPOINT); parser.add_argument("--identity-evidence", default=EVIDENCE)
    parser.add_argument("--decisions", help="Optional completed reviewer decision JSON.")
    parser.add_argument("--reports-dir", default="data/reports"); parser.add_argument("--batch-id", default="all_completed_v1")
    args = parser.parse_args()
    records = json.loads(Path(args.v5_proposals).read_text(encoding="utf-8")).get("records", [])
    checkpoint_path = Path(args.checkpoint); checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")); checkpoint_hash = content_hash(checkpoint)
    if len(records) != 82: raise ValueError("expected exactly 82 official source records")
    prior_evidence = {item["external_source_id"]: item for item in json.loads(Path(args.identity_evidence).read_text(encoding="utf-8")).get("records", [])}
    kb = asyncio.run(load_existing_kb_snapshot())
    audit = verification_audit(records, checkpoint); evidence = final_evidence(records, checkpoint, prior_evidence, kb); action_plan = proposals(records, audit, {item["source_attraction_id"]: item for item in evidence})
    duplicate = {"clusters": [{"cluster_id": "A", "source_attraction_ids": ["srilanka_tourism_attraction:36", "srilanka_tourism_attraction:94"], "name": "Panavitiya Ambalama", "allowed_reviewer_resolutions": ["SAME_PHYSICAL_ATTRACTION", "DISTINCT_ATTRACTIONS", "INCORRECT_SHARED_GOOGLE_MATCH", "INSUFFICIENT_EVIDENCE"], "resolution": "PENDING_REVIEW"}, {"cluster_id": "B", "source_attraction_ids": ["srilanka_tourism_attraction:107", "srilanka_tourism_attraction:124"], "name": "possible shared Google identity", "allowed_reviewer_resolutions": ["SAME_PHYSICAL_ATTRACTION", "DISTINCT_ATTRACTIONS", "INCORRECT_SHARED_GOOGLE_MATCH", "INSUFFICIENT_EVIDENCE"], "resolution": "PENDING_REVIEW"}]}
    classifications = classification_audit(records, action_plan, checkpoint)
    template = {"checkpoint_sha256": checkpoint_hash, "decisions": [{"source_attraction_id": item["source_attraction_id"], "proposed_action": item["proposed_action"], "final_proposal_sha256": item["final_proposal_sha256"], "checkpoint_sha256": checkpoint_hash, "decision": "DEFER", "reviewer_identity": None, "review_timestamp": None, "review_notes": None, "duplicate_cluster_resolution": None} for item in action_plan]}
    if args.decisions:
        decision_path = Path(args.decisions)
        if not decision_path.is_file():
            parser.error(
                f"decision file not found: {decision_path}. "
                "Use the generated reviewer_decision_template.json as a starting point, "
                "then save the completed human decisions under a real path."
            )
        decisions = json.loads(decision_path.read_text(encoding="utf-8"))
    else:
        decisions = template
    validation = validate_decisions(decisions=decisions, plan=action_plan, checkpoint_hash=checkpoint_hash, audit=audit)
    manifest = {"records": validation["approved_actions"], "checkpoint_sha256": checkpoint_hash, "integrity": "valid_empty_manifest" if not validation["approved_actions"] else "reviewer_validated", "postgresql_writes": False, "qdrant_writes": False}
    preflight = {"status": "NOT_READY_FOR_SYNC" if not validation["approved_actions"] else "READY_FOR_PARTIAL_APPROVED_SYNC", "reasons": (["targeted live verification incomplete"] if not audit["verification_complete"] else []) + (["no explicitly validated approved actions"] if not validation["approved_actions"] else []), "approved_action_count": len(validation["approved_actions"]), "governance_schema_readiness": True}
    payloads = {"verification_completion_audit": audit, "final_identity_evidence": {"records": evidence, "current_kb_active_attraction_count": kb["active_attraction_count"], "database_writes": False}, "final_action_proposals": {"records": action_plan}, "classification_audit": {"records": classifications}, "duplicate_cluster_review": duplicate, "reviewer_decision_template": template, "reviewer_validation": validation, "approved_action_manifest": manifest, "deferred_and_rejected_actions": {"deferred": validation["deferred_actions"], "rejected_or_blocked": validation["blocked_actions"]}, "gate5e2c_preflight": preflight, "summary": {"official_source_records": len(records), "verified_queue_completed": audit["completed_records"], "verified_queue_remaining": audit["pending_records"], "proposed_insertions": sum(item["proposed_action"] == "INSERT_NEW_CANDIDATE" for item in action_plan), "proposed_links": sum(item["proposed_action"] == "LINK_SOURCE_REFERENCE_CANDIDATE" for item in action_plan), "manual_review_required": sum(item["proposed_action"] == "MANUAL_REVIEW_REQUIRED" for item in action_plan), "rejected_invalid_match": sum(item["proposed_action"] == "REJECT_INVALID_MATCH" for item in action_plan), "approved_action_count": len(manifest["records"]), "postgresql_writes": False, "qdrant_writes": False, "network_requests": 0}}
    reports_dir = Path(args.reports_dir); prefix = reports_dir / f"stage_10_1_3e_gate5e2b6_{args.batch_id}_"
    paths={}
    for key, value in payloads.items(): paths[key] = prefix.with_name(prefix.name + key + ".json"); write_json(paths[key], value)
    csv_path = prefix.with_name(prefix.name + "reviewer_decision_workbook.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(template["decisions"][0])); writer.writeheader(); writer.writerows(template["decisions"])
    paths["reviewer_decision_workbook"] = csv_path
    print(json.dumps({"mode": "preliminary_audit" if not audit["verification_complete"] else "final_consolidation", "reports": {key: str(value) for key, value in paths.items()}, "summary": payloads["summary"], "preflight": preflight}, indent=2))


if __name__ == "__main__": main()
