"""Bounded, checkpoint-safe Gate 5E.2B.5 Google Places verification.

The command is review-only: it never opens PostgreSQL or Qdrant. Network access
is disabled unless all three explicit live-execution flags are supplied.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.time_context.governance.tourism_sync_approval import digest

DEFAULT_QUEUE = "data/reports/stage_10_1_3e_gate5e2b4_all_completed_v1_targeted_live_verification_queue.json"
DEFAULT_V4 = "data/reports/stage_10_1_3e_gate5e2b4_all_completed_v1_corrected_proposals_v4.json"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _queue_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _normalise(value: str) -> str:
    return " ".join("".join(char.lower() if char.isalnum() else " " for char in value).split())


def _candidate_name(candidate: dict[str, Any]) -> str:
    display = candidate.get("displayName") or {}
    return str(display.get("text") if isinstance(display, dict) else display or "")


def assess_candidates(record: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate candidate evidence without approving an identity or action."""
    if not candidates:
        return {"assessment": "NO_VALID_GOOGLE_CANDIDATE", "reason": "Google text search returned no candidates.", "shortlisted_place_id": None}
    first = candidates[0]
    types = {str(item).lower() for item in first.get("types", [])}
    primary = str(first.get("primaryType") or "").lower()
    if any(mark in record["official_name"].lower() for mark in (" & ", " and ", "/")):
        return {"assessment": "COMPOUND_SOURCE_REVIEW_REQUIRED", "reason": "The official title can refer to multiple places.", "shortlisted_place_id": first.get("id")}
    if primary in {"locality", "country"} or types & {"locality", "political", "administrative_area_level_1", "administrative_area_level_2"}:
        return {"assessment": "RELATED_LOCALITY_NOT_ATTRACTION", "reason": "A locality or administrative area cannot alone establish attraction identity.", "shortlisted_place_id": first.get("id")}
    if _normalise(_candidate_name(first)) == _normalise(record["official_name"]):
        return {"assessment": "EXACT_NAME_CANDIDATE_REVIEW_REQUIRED", "reason": "Exact name remains candidate evidence pending location/source review.", "shortlisted_place_id": first.get("id")}
    return {"assessment": "PLAUSIBLE_IDENTITY_FOR_HUMAN_REVIEW", "reason": "Name similarity alone is not identity proof.", "shortlisted_place_id": first.get("id")}


def _load_checkpoint(queue_path: Path, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {"version": 1, "queue_sha256": _queue_hash(queue_path), "completed_source_ids": [], "failed_source_ids": [], "results": [], "cumulative_requests": 0}
    if checkpoint.get("queue_sha256") != _queue_hash(queue_path):
        raise ValueError("checkpoint queue SHA-256 does not match the supplied verification queue")
    completed = checkpoint.get("completed_source_ids", [])
    if len(completed) != len(set(completed)):
        raise ValueError("checkpoint contains duplicate completed source IDs")
    return checkpoint


async def execute_verification(*, queue: list[dict[str, Any]], checkpoint: dict[str, Any], checkpoint_path: Path, live: bool, max_requests: int, max_records: int, client: Any | None = None) -> dict[str, Any]:
    """Process at most ``max_records`` while atomically checkpointing each success."""
    if not 1 <= max_requests <= 60:
        raise ValueError("max_requests must be between 1 and 60")
    if not 1 <= max_records <= 30:
        raise ValueError("max_records must be between 1 and 30")
    if checkpoint["cumulative_requests"] > max_requests:
        raise ValueError("checkpoint already exceeds the requested cumulative API budget")
    known = {item["source_attraction_id"] for item in queue}
    if not set(checkpoint["completed_source_ids"]).issubset(known):
        raise ValueError("checkpoint contains source IDs not present in the verification queue")
    if not live:
        return checkpoint
    if client is None:
        raise ValueError("a live verification client is required")
    completed, processed = set(checkpoint["completed_source_ids"]), 0
    for item in queue:
        source_id = item["source_attraction_id"]
        if source_id in completed:
            continue
        if processed >= max_records or checkpoint["cumulative_requests"] >= max_requests:
            break
        query = (item.get("queries") or [item["official_name"]])[0] + ", Sri Lanka"
        try:
            checkpoint["cumulative_requests"] += 1
            candidates = await client.text_search(query=query, max_results=5)
            assessment = assess_candidates(item, candidates)
            details = None
            if assessment["shortlisted_place_id"] and checkpoint["cumulative_requests"] < max_requests and item.get("max_api_requests", 2) >= 2:
                checkpoint["cumulative_requests"] += 1
                details = await client.get_place_details(assessment["shortlisted_place_id"])
            checkpoint["results"].append({"source_attraction_id": source_id, "official_name": item["official_name"], "query": query, "candidates": candidates, "shortlisted_details": details, **assessment, "error": None})
            completed.add(source_id); checkpoint["completed_source_ids"] = sorted(completed)
            _write_json(checkpoint_path, checkpoint); processed += 1
        except Exception as error:
            checkpoint["failed_source_ids"] = sorted(set(checkpoint.get("failed_source_ids", [])) | {source_id})
            checkpoint["last_error"] = {"source_attraction_id": source_id, "error": f"{type(error).__name__}: {error}"}
            _write_json(checkpoint_path, checkpoint)
            break
    return checkpoint


def _v5_proposals(v4_path: Path, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prior = json.loads(v4_path.read_text(encoding="utf-8")).get("records", []) if v4_path.exists() else []
    evidence = {item["source_attraction_id"]: item for item in results}
    output = []
    for record in prior:
        item, result = dict(record), evidence.get(record["source_attraction_id"])
        # B.5 verifies only the 30 targeted uncertain records.  It must not
        # silently downgrade the remaining B.4 insert/link candidates merely
        # because they were outside that live-verification queue.
        prior_action = item.get("corrected_proposed_action", "MANUAL_REVIEW_REQUIRED")
        item.update({"proposal_version": "v5", "new_evidence_collected": result is not None, "live_verification_assessment": result.get("assessment") if result else "NOT_YET_VERIFIED", "corrected_proposed_action": prior_action, "human_review_status": "DEFER", "reviewer_status": "DEFER"})
        item["v5_proposal_sha256"] = digest({key: value for key, value in item.items() if key not in {"v5_proposal_sha256", "corrected_proposal_sha256"}})
        output.append(item)
    return output


def write_reports(*, reports_dir: Path, batch_id: str, queue: list[dict[str, Any]], checkpoint: dict[str, Any], max_requests: int, v4_path: Path, live: bool) -> dict[str, Path]:
    prefix = reports_dir / f"stage_10_1_3e_gate5e2b5_{batch_id}_"
    completed, results = set(checkpoint["completed_source_ids"]), checkpoint["results"]
    clusters: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if result.get("shortlisted_place_id"):
            clusters[result["shortlisted_place_id"]].append(result["source_attraction_id"])
    proposals = _v5_proposals(v4_path, results)
    reviewer = [{"source_attraction_id": item["source_attraction_id"], "proposed_action": "MANUAL_REVIEW_REQUIRED", "reviewer_decision": "DEFER", "proposal_sha256": item["v5_proposal_sha256"]} for item in proposals]
    remaining = [item["source_attraction_id"] for item in queue if item["source_attraction_id"] not in completed]
    payloads: dict[str, Any] = {
        "api_usage": {"cumulative_requests": checkpoint["cumulative_requests"], "maximum_request_budget": max_requests, "within_budget": checkpoint["cumulative_requests"] <= max_requests, "network_requests": checkpoint["cumulative_requests"] if live else 0},
        "live_search_results": {"records": results, "raw_response_provenance_preserved": True},
        "candidate_identity_assessment": {"records": results, "automatic_approval_performed": False},
        "corrected_proposals_v5": {"records": proposals, "database_writes": False, "qdrant_writes": False},
        "duplicate_cluster_evidence": {"clusters": [{"google_place_id": key, "source_attraction_ids": value} for key, value in sorted(clusters.items()) if len(value) > 1]},
        "remaining_identity_blockers": {"source_ids": remaining, "failed_source_ids": checkpoint.get("failed_source_ids", [])},
        "reviewer_decision_template": {"decisions": reviewer},
        "approval_validation": {"approved_actions": [], "status": "NO_APPROVALS_APPLIED"},
        "approved_action_manifest": {"records": [], "integrity": "valid_empty_manifest", "database_writes": False},
        "gate5e2c_preflight": {"status": "NOT_READY_FOR_SYNC", "reason": "No reviewer-approved, checksum-bound action manifest exists."},
        "summary": {"queue_records": len(queue), "completed": len(completed), "remaining": len(remaining), "failed": len(checkpoint.get("failed_source_ids", [])), "cumulative_requests": checkpoint["cumulative_requests"], "maximum_request_budget": max_requests, "postgresql_writes": False, "qdrant_writes": False},
    }
    paths = {key: prefix.with_name(prefix.name + key + ".json") for key in payloads}
    for key, payload in payloads.items(): _write_json(paths[key], payload)
    csv_path = prefix.with_name(prefix.name + "reviewer_decision_workbook.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_attraction_id", "proposed_action", "reviewer_decision", "proposal_sha256"]); writer.writeheader(); writer.writerows(reviewer)
    paths["reviewer_decision_workbook"] = csv_path
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default=DEFAULT_QUEUE); parser.add_argument("--v4-proposals", default=DEFAULT_V4)
    parser.add_argument("--checkpoint", default="data/reports/stage_10_1_3e_gate5e2b5_all_completed_v1_verification_checkpoint.json")
    parser.add_argument("--reports-dir", default="data/reports"); parser.add_argument("--batch-id", default="all_completed_v1")
    parser.add_argument("--max-requests", type=int, default=60); parser.add_argument("--max-records", type=int, default=5)
    parser.add_argument("--live", action="store_true"); parser.add_argument("--execute", action="store_true"); parser.add_argument("--confirm-execute", action="store_true")
    args = parser.parse_args()
    if args.live and not (args.execute and args.confirm_execute): raise PermissionError("live mode requires --live --execute --confirm-execute")
    queue_path, checkpoint_path = Path(args.queue), Path(args.checkpoint)
    queue = json.loads(queue_path.read_text(encoding="utf-8")).get("records", [])
    checkpoint = _load_checkpoint(queue_path, checkpoint_path)
    client = None
    if args.live:
        from app.knowledge_base.connectors.google_places import GooglePlacesConnector
        client = GooglePlacesConnector()
    checkpoint = asyncio.run(execute_verification(queue=queue, checkpoint=checkpoint, checkpoint_path=checkpoint_path, live=args.live, max_requests=args.max_requests, max_records=args.max_records, client=client))
    paths = write_reports(reports_dir=Path(args.reports_dir), batch_id=args.batch_id, queue=queue, checkpoint=checkpoint, max_requests=args.max_requests, v4_path=Path(args.v4_proposals), live=args.live)
    print(json.dumps({"mode": "live" if args.live else "offline", "checkpoint": str(checkpoint_path), "reports": {key: str(path) for key, path in paths.items()}, "summary": json.loads(paths["summary"].read_text(encoding="utf-8"))}, indent=2))


if __name__ == "__main__": main()
