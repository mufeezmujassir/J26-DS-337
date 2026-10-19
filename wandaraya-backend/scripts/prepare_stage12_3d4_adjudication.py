"""Prepare a separate, immutable-raw-label adjudication workbook."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path("data/reports")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-1", default=str(ROOT / "stage12_3d4_r1_blind_template.csv"))
    parser.add_argument("--reviewer-2", default=str(ROOT / "stage12_3d4_r2_blind_template.csv"))
    parser.add_argument("--output", default=str(ROOT / "stage12_3d4_adjudication_template.csv"))
    args = parser.parse_args()
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for source in (args.reviewer_1, args.reviewer_2):
        for row in csv.DictReader(Path(source).open(encoding="utf-8", newline="")):
            grouped[(row["query_id"], row["attraction_id"])].append(row)
    fields = ["query_id", "travel_date", "interests", "attraction_id", "attraction_name", "district_id", "categories", "activities", "r1_relevance_0_to_3", "r1_explanation", "r2_relevance_0_to_3", "r2_explanation", "adjudicated_relevance_0_to_3", "adjudicator_id", "adjudication_reason"]
    conflicts = []
    for _, values in sorted(grouped.items()):
        by_reviewer = {value.get("reviewer_id"): value for value in values}
        r1, r2 = by_reviewer.get("R1"), by_reviewer.get("R2")
        if not r1 or not r2: continue
        if r1.get("relevance_0_to_3", "").strip() != r2.get("relevance_0_to_3", "").strip():
            conflicts.append({"query_id": r1["query_id"], "travel_date": r1["travel_date"], "interests": r1["interests"], "attraction_id": r1["attraction_id"], "attraction_name": r1["attraction_name"], "district_id": r1["district_id"], "categories": r1["categories"], "activities": r1["activities"], "r1_relevance_0_to_3": r1["relevance_0_to_3"], "r1_explanation": r1.get("reviewer_explanation", ""), "r2_relevance_0_to_3": r2["relevance_0_to_3"], "r2_explanation": r2.get("reviewer_explanation", ""), "adjudicated_relevance_0_to_3": "", "adjudicator_id": "", "adjudication_reason": ""})
    with Path(args.output).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(conflicts)
    print({"status": "ADJUDICATION_TEMPLATE_READY", "conflicts": len(conflicts), "output": args.output, "raw_reviewer_files_modified": False})


if __name__ == "__main__":
    main()
