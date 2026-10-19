"""Create non-binding, transparent suggestions for human adjudication."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path("data/reports")


def suggestion(left: int, right: int) -> tuple[str, str]:
    gap = abs(left - right)
    if gap == 1:
        return str(round((left + right) / 2)), "Machine suggestion only: adjacent reviewer scores; human adjudicator must confirm or replace."
    return "", "No machine score suggested: reviewer disagreement is material; human adjudicator must decide from factual evidence."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "stage12_3d4_adjudication_template.csv"))
    parser.add_argument("--output", default=str(ROOT / "stage12_3d4_adjudication_suggestions.csv"))
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8", newline="")))
    fields = list(rows[0]) + ["machine_suggested_relevance_0_to_3", "machine_suggestion_reason", "machine_suggestion_provenance"] if rows else []
    for row in rows:
        proposed, reason = suggestion(int(row["r1_relevance_0_to_3"]), int(row["r2_relevance_0_to_3"]))
        row["machine_suggested_relevance_0_to_3"] = proposed
        row["machine_suggestion_reason"] = reason
        row["machine_suggestion_provenance"] = "NON_BINDING_MACHINE_SUGGESTION_NOT_A_HUMAN_DECISION"
    with Path(args.output).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print({"status": "SUGGESTION_WORKSHEET_READY", "conflicts": len(rows), "suggestions_provided": sum(bool(row["machine_suggested_relevance_0_to_3"]) for row in rows), "human_decisions_written": 0, "output": args.output})


if __name__ == "__main__":
    main()
