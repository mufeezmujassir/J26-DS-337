"""Gate 5E.2C.3: read-only PostgreSQL synchronization planning.

The default and only enabled behaviour is a database-read-only dry run.  The
future write flags are intentionally rejected: no approved tourism attraction
is inserted by this command.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.categories import Category
from app.models.district import District
from app.models.tourism_sync import AttractionSourceReference


BASE = "data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_"
B1 = "data/reports/stage_10_1_3e_gate5e2b1_all_completed_v1_identity_evidence_manifest.json"
B6 = "data/reports/stage_10_1_3e_gate5e2b6_all_completed_v1_approved_action_manifest.json"


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def slug_for(name: str, source_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:200] or "tourism-attraction"
    return f"{base}-{sha256(source_id.encode()).hexdigest()[:10]}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def validate_manifest(*, approved: list[dict[str, Any]], enriched: list[dict[str, Any]], upstream: list[dict[str, Any]], validation: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    enriched_by_id = {row["source_attraction_id"]: row for row in enriched}
    upstream_by_id = {row["source_attraction_id"]: row for row in upstream}
    blocked_ids = {row.get("source_attraction_id") for row in validation.get("blocked", [])}
    valid, invalid, seen = [], [], set()
    for row in approved:
        source_id, reasons = row.get("source_attraction_id"), []
        evidence, original = enriched_by_id.get(source_id), upstream_by_id.get(source_id)
        if not source_id or source_id in seen: reasons.append("duplicate_or_missing_source_attraction_id")
        seen.add(source_id)
        if source_id in blocked_ids: reasons.append("source_appears_in_blocked_reapproval_list")
        if row.get("approved_action") != "INSERT_NEW_CANDIDATE": reasons.append("approved_action_is_not_insert")
        if not evidence: reasons.append("missing_enriched_evidence")
        if not original: reasons.append("missing_upstream_approval")
        if evidence:
            for key in ("original_approval_hash", "revised_proposal_sha256", "enrichment_evidence_sha256", "district_id", "category_id", "google_place_id"):
                if not row.get(key): reasons.append(f"missing_{key}")
            if row.get("original_approval_hash") != evidence.get("original_approval_hash"): reasons.append("original_approval_hash_mismatch")
            if row.get("revised_proposal_sha256") != evidence.get("revised_proposal_sha256"): reasons.append("revised_proposal_hash_mismatch")
            if row.get("enrichment_evidence_sha256") != evidence.get("enrichment_evidence_sha256"): reasons.append("enrichment_evidence_hash_mismatch")
            unsafe = [x for x in evidence.get("conflicts", []) if x != "district_derived_from_saved_gate5d_evidence_requires_reapproval"]
            if unsafe: reasons.extend(unsafe)
        if original and row.get("upstream_final_proposal_sha256") != original.get("final_proposal_sha256"): reasons.append("stale_upstream_approval_hash")
        if row.get("reviewer_decision") != "APPROVE_INSERT_AFTER_CATEGORY_EVIDENCE": reasons.append("invalid_reviewer_approval")
        if not row.get("reviewer_identity") or not row.get("review_timestamp") or not row.get("review_notes"): reasons.append("incomplete_reviewer_evidence")
        (invalid if reasons else valid).append({"action": row, "evidence": evidence, "reasons": sorted(set(reasons))})
    return valid, invalid


async def db_snapshot() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        districts = {row.id: row.name for row in (await session.execute(select(District).where(District.is_active.is_(True)))).scalars()}
        categories = {row.id: row.name for row in (await session.execute(select(Category).where(Category.is_active.is_(True)))).scalars()}
        attractions = [{"id": row.id, "name": row.name, "google_place_id": row.google_place_id, "district_id": row.district_id, "latitude": row.latitude, "longitude": row.longitude} for row in (await session.execute(select(Attraction).where(Attraction.is_active.is_(True)))).scalars()]
        references = [{"attraction_id": row.attraction_id, "external_source_id": row.external_source_id, "source_provider": row.source_provider} for row in (await session.execute(select(AttractionSourceReference).where(AttractionSourceReference.source_provider == "srilanka_tourism"))).scalars()]
    return {"districts": districts, "categories": categories, "attractions": attractions, "references": references}


def resolve_and_audit(*, valid: list[dict[str, Any]], prior: dict[str, dict[str, Any]], snapshot: dict[str, Any], batch_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_google: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in snapshot["attractions"]:
        if row["google_place_id"]: by_google.setdefault(row["google_place_id"], []).append(row)
        by_name.setdefault(norm(row["name"]), []).append(row)
    by_source = {row["external_source_id"]: row for row in snapshot["references"]}
    payloads, audits, batch_google = [], [], set()
    for item in valid:
        action, evidence = item["action"], item["evidence"]
        source_id, source = action["source_attraction_id"], prior.get(action["source_attraction_id"], {})
        reasons: list[str] = []
        name, source_url = evidence.get("official_name"), evidence.get("official_source_url")
        if not name: reasons.append("missing_official_attraction_name")
        if not source_url: reasons.append("missing_official_source_url")
        if action["district_id"] not in snapshot["districts"]: reasons.append("district_id_not_active")
        if action["category_id"] not in snapshot["categories"]: reasons.append("category_id_not_active")
        google_id = action["google_place_id"]
        if google_id in batch_google: reasons.append("duplicate_google_place_id_inside_approved_batch")
        batch_google.add(google_id)
        source_hit, google_hits, name_hits = by_source.get(source_id), by_google.get(google_id, []), by_name.get(norm(name), [])
        classification = "NEW_INSERT_READY"
        if source_hit:
            classification = "ALREADY_IMPORTED_SAME_IDENTITY" if source_hit.get("attraction_id") in [x["id"] for x in google_hits] else "CONFLICTING_EXISTING_IDENTITY"
        elif google_hits:
            classification = "EXISTING_ATTRACTION_REQUIRES_LINK_REVIEW"
        elif name_hits:
            classification = "EXISTING_ATTRACTION_REQUIRES_LINK_REVIEW"
        if reasons: classification = "INVALID_OR_INCOMPLETE"
        payload = {"source_attraction_id": source_id, "name": name, "slug": slug_for(name or "", source_id), "google_place_id": google_id, "latitude": evidence.get("latitude"), "longitude": evidence.get("longitude"), "location": {"latitude": evidence.get("latitude"), "longitude": evidence.get("longitude"), "source": "saved_google_places_evidence"}, "district_id": action["district_id"], "category_id": action["category_id"], "official_source_url": source_url, "source_provider": "srilanka_tourism", "source_title": name, "import_batch_id": batch_id, "field_provenance": ["name", "google_place_id", "latitude", "longitude", "district_id", "category_id", "official_source_url"]}
        if classification == "NEW_INSERT_READY": payloads.append(payload)
        audits.append({"source_attraction_id": source_id, "classification": classification, "reasons": reasons, "existing_source_reference": source_hit, "google_place_matches": google_hits, "normalized_name_matches": name_hits, "payload": payload})
    return payloads, audits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--manifest", default=BASE + "reapproved_action_manifest.json")
    parser.add_argument("--dry-run", action="store_true", help="Required; performs reads only.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--reports-dir", default="data/reports")
    args = parser.parse_args()
    if args.execute or args.confirm_execute:
        parser.error("Gate 5E.2C.3 write execution is intentionally disabled; this implementation supports dry-run only.")
    if not args.dry_run:
        parser.error("--dry-run is required; default behaviour is read-only.")
    manifest_path = Path(args.manifest)
    approved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enriched = json.loads(Path(BASE + "metadata_enrichment_manifest.json").read_text(encoding="utf-8")).get("records", [])
    upstream = json.loads(Path(B6).read_text(encoding="utf-8")).get("records", [])
    validation = json.loads(Path(BASE + "reapproval_validation.json").read_text(encoding="utf-8"))
    prior = {row["external_source_id"]: row for row in json.loads(Path(B1).read_text(encoding="utf-8")).get("records", [])}
    valid, invalid = validate_manifest(approved=approved_manifest.get("records", []), enriched=enriched, upstream=upstream, validation=validation)
    snapshot = asyncio.run(db_snapshot())
    payloads, collisions = resolve_and_audit(valid=valid, prior=prior, snapshot=snapshot, batch_id=args.batch_id)
    ready_ids = {payload["source_attraction_id"] for payload in payloads}
    plan = {"mode": "dry_run_only", "operations": [{"operation": "INSERT attraction", "source_attraction_id": p["source_attraction_id"]} for p in payloads], "planned_category_links": len(payloads), "planned_source_references": len(payloads), "planned_provenance_records": len(payloads) * 7, "writes_executed": False}
    prefix = Path(args.reports_dir) / f"stage_10_1_3e_gate5e2c3_{args.batch_id}_"
    manifest_sha = file_digest(manifest_path); plan_sha = digest(plan)
    reports = {
        "manifest_integrity_validation": {"valid": len(valid), "invalid": invalid, "manifest_sha256": manifest_sha},
        "resolved_insert_payloads": {"records": payloads},
        "existing_attraction_collision_audit": {"records": collisions},
        "source_reference_collision_audit": {"records": [row for row in collisions if row["existing_source_reference"]]},
        "transaction_execution_plan": {**plan, "dry_run_plan_sha256": plan_sha},
        "dry_run_results": {"ready_source_attraction_ids": sorted(ready_ids), "writes_executed": False, "qdrant_writes_executed": False, "external_api_requests": 0},
        "blocked_and_skipped_actions": {"records": invalid + [{"source_attraction_id": row["source_attraction_id"], "classification": row["classification"], "reasons": row["reasons"]} for row in collisions if row["source_attraction_id"] not in ready_ids]},
        "write_authorization_requirements": {"required": ["--execute", "--confirm-execute", "exact manifest SHA-256", "exact dry-run plan SHA-256", "fresh collision preflight", "explicit human scope"], "write_execution_enabled": False},
        "summary": {"approved_manifest_count": len(approved_manifest.get("records", [])), "fully_resolved_payloads": len(payloads), "ready_insertions": len(payloads), "already_imported_actions": sum(row["classification"] == "ALREADY_IMPORTED_SAME_IDENTITY" for row in collisions), "identity_conflicts": sum(row["classification"] in {"CONFLICTING_EXISTING_IDENTITY", "EXISTING_ATTRACTION_REQUIRES_LINK_REVIEW"} for row in collisions), "invalid_payloads": len(invalid) + sum(row["classification"] == "INVALID_OR_INCOMPLETE" for row in collisions), "existing_active_attraction_count": len(snapshot["attractions"]), "estimated_active_attraction_count_after": len(snapshot["attractions"]) + len(payloads), "manifest_sha256": manifest_sha, "dry_run_plan_sha256": plan_sha, "postgresql_writes_executed": False, "qdrant_writes_executed": False, "external_api_requests": 0},
    }
    paths = {}
    for name, value in reports.items():
        path = prefix.with_name(prefix.name + name + ".json"); write_json(path, value); paths[name] = str(path)
    print(json.dumps({"mode": "dry_run", "summary": reports["summary"], "reports": paths}, indent=2))


if __name__ == "__main__":
    main()
