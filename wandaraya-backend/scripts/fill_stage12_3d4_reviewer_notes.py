"""Fill optional standard notes after a human has supplied a relevance score.

This helper never assigns relevance scores and never changes identity or
candidate fields.  It only fills blank reviewer_explanation cells.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


TEMPLATES = {
    "0": "Irrelevant to the stated tourism request based on the visible factual evidence.",
    "1": "Weakly relevant: there is a limited connection to the stated tourism request.",
    "2": "Relevant: the visible factual evidence supports a material part of the stated tourism request.",
    "3": "Highly relevant: the visible factual evidence directly and strongly fits the stated tourism request.",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes; omit for a read-only preview.")
    args = parser.parse_args()
    path = Path(args.file)
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    fields = list(rows[0]) if rows else []
    filled = skipped = 0
    for row in rows:
        score = row.get("relevance_0_to_3", "").strip()
        cannot_judge = row.get("cannot_judge", "").strip().casefold() in {"true", "yes", "1"}
        if row.get("reviewer_explanation", "").strip() or (not score and not cannot_judge):
            skipped += 1
            continue
        reviewer = row.get("reviewer_id", "Reviewer").strip() or "Reviewer"
        if cannot_judge:
            row["reviewer_explanation"] = f"{reviewer}: cannot judge from the factual information available in this blinded row."
        elif score in TEMPLATES:
            row["reviewer_explanation"] = f"{reviewer}: {TEMPLATES[score]}"
        else:
            skipped += 1
            continue
        filled += 1
    if args.apply:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    print({"mode": "apply" if args.apply else "preview", "file": str(path), "notes_filled": filled, "rows_skipped": skipped, "scores_assigned": 0})


if __name__ == "__main__":
    main()
