"""Validate Gate 5E.2C.2 reviewer reapprovals without performing any writes.

This is deliberately an approval boundary: a reviewer decision can make a
metadata-complete proposal *eligible for a later explicitly authorised write*,
but it cannot insert attractions, update PostgreSQL, call Google, or update
Qdrant.  The script accepts either the generated JSON review template or its
CSV equivalent and emits an immutable, hash-bound approved-action manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


BASE = "data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_"
UPSTREAM_MANIFEST = "data/reports/stage_10_1_3e_gate5e2b6_all_completed_v1_approved_action_manifest.json"
APPROVAL = "APPROVE_INSERT_AFTER_CATEGORY_EVIDENCE"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def load_decisions(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("decision file must contain a JSON object with a records list")
    return payload["records"]


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate(*, enriched: list[dict[str, Any]], decisions: list[dict[str, Any]], upstream: list[dict[str, Any]]) -> dict[str, Any]:
    enriched_by_id = {record["source_attraction_id"]: record for record in enriched}
    upstream_by_id = {record["source_attraction_id"]: record for record in upstream}
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen: set[str] = set()

    for decision in decisions:
        source_id = decision.get("source_attraction_id")
        reasons: list[str] = []
        record = enriched_by_id.get(source_id)
        original = upstream_by_id.get(source_id)
        if not source_id or source_id in seen:
            reasons.append("duplicate_or_missing_source_attraction_id")
        seen.add(source_id)
        if record is None:
            reasons.append("source_not_present_in_current_enrichment_manifest")
        if original is None:
            reasons.append("source_not_present_in_upstream_approved_manifest")
        if record and decision.get("revised_proposal_sha256") != record.get("revised_proposal_sha256"):
            reasons.append("stale_or_modified_revised_proposal_hash")
        if record and decision.get("original_approval_hash") != record.get("original_approval_hash"):
            reasons.append("stale_or_modified_original_approval_hash")
        if decision.get("decision") != APPROVAL:
            reasons.append("not_explicitly_reapproved")
        if not decision.get("reviewer_identity"):
            reasons.append("reviewer_identity_missing")
        if not valid_timestamp(decision.get("review_timestamp")):
            reasons.append("review_timestamp_must_be_timezone_aware_iso8601")
        if not decision.get("review_notes") or decision.get("review_notes") == "Record the official-source and Google evidence reviewed.":
            reasons.append("specific_reviewer_notes_required")

        if record:
            unsafe = [conflict for conflict in record.get("conflicts", []) if conflict != "district_derived_from_saved_gate5d_evidence_requires_reapproval"]
            if unsafe:
                reasons.extend(unsafe)
            if record.get("district_evidence", {}).get("status") != "verified":
                reasons.append("missing_verified_district")
            if not record.get("category_id"):
                reasons.append("missing_verified_category")
            if not record.get("reapproval_required"):
                reasons.append("no_material_change_requires_reapproval")

        summary = {"source_attraction_id": source_id, "decision": decision.get("decision"), "reasons": sorted(set(reasons))}
        if reasons:
            blocked.append(summary)
            continue
        approved.append({
            "source_attraction_id": source_id,
            "approved_action": original["approved_action"],
            "upstream_final_proposal_sha256": original["final_proposal_sha256"],
            "original_approval_hash": record["original_approval_hash"],
            "revised_proposal_sha256": record["revised_proposal_sha256"],
            "enrichment_evidence_sha256": record["enrichment_evidence_sha256"],
            "district_id": record["district_id"],
            "category_id": record["category_id"],
            "google_place_id": record.get("google_place_id"),
            "reviewer_decision": APPROVAL,
            "reviewer_identity": decision["reviewer_identity"],
            "review_timestamp": decision["review_timestamp"],
            "review_notes": decision["review_notes"],
        })
    missing = sorted(set(enriched_by_id).intersection(upstream_by_id).difference(seen))
    blocked.extend({"source_attraction_id": source_id, "decision": None, "reasons": ["missing_reviewer_decision"]} for source_id in missing)
    return {"approved": approved, "blocked": blocked}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", required=True, help="Reviewed .json or .csv template; no decisions are inferred.")
    parser.add_argument("--enrichment-manifest", default=BASE + "metadata_enrichment_manifest.json")
    parser.add_argument("--upstream-manifest", default=UPSTREAM_MANIFEST)
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--batch-id", default="all_completed_v1")
    args = parser.parse_args()

    enriched = json.loads(Path(args.enrichment_manifest).read_text(encoding="utf-8")).get("records", [])
    upstream = json.loads(Path(args.upstream_manifest).read_text(encoding="utf-8")).get("records", [])
    result = validate(enriched=enriched, decisions=load_decisions(Path(args.decisions)), upstream=upstream)
    prefix = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2c2_{args.batch_id}_"
    manifest = {"records": result["approved"], "writes_executed": False, "qdrant_writes_executed": False, "external_api_requests": 0}
    # Readiness applies to the explicit approved subset.  A remaining deferred
    # or unsafe record must stay quarantined, but it must not prevent a
    # separately reviewed, hash-valid record from proceeding to the later
    # explicitly-authorised write stage.
    preflight = {
        "dry_run": True,
        "postgresql_writes": False,
        "qdrant_writes": False,
        "status": "READY_FOR_EXPLICITLY_AUTHORIZED_WRITE" if result["approved"] else "NOT_READY_FOR_WRITE",
        "reasons": (["blocked records remain excluded from the approved write scope"] if result["approved"] and result["blocked"] else []) if result["approved"] else ["no hash-valid explicit reapprovals are available"],
    }
    paths = {
        "approval_validation": prefix.with_name(prefix.name + "reapproval_validation.json"),
        "approved_action_manifest": prefix.with_name(prefix.name + "reapproved_action_manifest.json"),
        "preflight": prefix.with_name(prefix.name + "reapproval_preflight.json"),
    }
    write_json(paths["approval_validation"], {"approved": result["approved"], "blocked": result["blocked"]})
    write_json(paths["approved_action_manifest"], manifest)
    write_json(paths["preflight"], preflight)
    print(json.dumps({"mode": "offline_reapproval_validation", "approved": len(result["approved"]), "blocked": len(result["blocked"]), "preflight": preflight, "reports": {key: str(value) for key, value in paths.items()}}, indent=2))


if __name__ == "__main__":
    main()
