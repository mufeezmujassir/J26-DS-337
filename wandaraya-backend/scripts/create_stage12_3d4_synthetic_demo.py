"""Create transparently synthetic labels for importer smoke tests only.

These outputs are not human annotations and must never be substituted into the
R1/R2 independent-review templates or used for research metrics.
"""
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path("data/reports")


def score(row: dict, reviewer: str) -> tuple[int, str]:
    """A transparent lexical fixture, deliberately not a relevance judgment."""
    interests = {item.strip().casefold() for item in row["interests"].split("|") if item.strip()}
    facts = " ".join((row.get("attraction_name", ""), row.get("categories", ""), row.get("activities", ""))).casefold()
    overlaps = sum(term in facts for term in interests)
    # A tiny deterministic reviewer difference only exercises disagreement
    # detection; it must not be presented as independent human behaviour.
    adjustment = 1 if reviewer == "R2" and int(row["attraction_id"]) % 17 == 0 else 0
    return min(3, overlaps + adjustment), "SYNTHETIC TEST FIXTURE ONLY — lexical overlap; not a human relevance judgment."


def main() -> None:
    for reviewer in ("R1", "R2"):
        source = ROOT / f"stage12_3d4_{reviewer.lower()}_blind_template.csv"
        target = ROOT / f"stage12_3d4_{reviewer.lower()}_synthetic_demo.csv"
        rows = list(csv.DictReader(source.open(encoding="utf-8", newline="")))
        fields = list(rows[0]) + ["annotation_provenance"]
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
            for row in rows:
                value, note = score(row, reviewer)
                row["relevance_0_to_3"] = value
                row["reviewer_explanation"] = note
                row["annotation_provenance"] = "SYNTHETIC_TEST_ONLY_NOT_INDEPENDENT_HUMAN_LABEL"
                writer.writerow(row)
        print(target)


if __name__ == "__main__":
    main()
