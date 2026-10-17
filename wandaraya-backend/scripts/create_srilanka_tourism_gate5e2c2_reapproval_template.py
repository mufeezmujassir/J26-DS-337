"""Create a human-review template for material Gate 5E.2C.2 metadata changes.

This command is offline-only.  It does not alter proposals, make API calls, or
write PostgreSQL/Qdrant.  The template is evidence for a later validator; it
does not itself approve a synchronization.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_reapproval_required_actions.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def decisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for record in records:
        output.append({
            "source_attraction_id": record["source_attraction_id"],
            "official_name": record.get("official_name"),
            "original_approval_hash": record.get("original_approval_hash"),
            "revised_proposal_sha256": record.get("revised_proposal_sha256"),
            "district_id": record.get("district_id"),
            "district_name": record.get("district_evidence", {}).get("district_name"),
            "category_id": record.get("category_id"),
            "category_name": record.get("proposed_category_name"),
            "blockers": record.get("conflicts", []),
            # No currently emitted record is safe to approve: category evidence
            # remains incomplete.  Keep an explicit default, never auto-approve.
            "decision": "DEFER",
            "reviewer_identity": "MUFEEZ",
            "review_timestamp": "2026-10-17T14:45:00+05:30",
            "review_notes": "Record the official-source and Google evidence reviewed.",
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-json", default="data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_reapproval_decision_template.json")
    parser.add_argument("--output-csv", default="data/reports/stage_10_1_3e_gate5e2c2_all_completed_v1_reapproval_decision_template.csv")
    args = parser.parse_args()
    records = json.loads(Path(args.input).read_text(encoding="utf-8")).get("records", [])
    rows = decisions(records)
    payload = {"mode": "human_review_template", "automatic_approval_performed": False, "allowed_decisions": ["DEFER", "REJECT_INVALID_MATCH", "APPROVE_INSERT_AFTER_CATEGORY_EVIDENCE"], "records": rows}
    write_json(Path(args.output_json), payload)
    with Path(args.output_csv).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["source_attraction_id", "decision"])
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"mode": "human_review_template", "records": len(rows), "automatic_approval_performed": False, "json": args.output_json, "csv": args.output_csv}, indent=2))


if __name__ == "__main__":
    main()
