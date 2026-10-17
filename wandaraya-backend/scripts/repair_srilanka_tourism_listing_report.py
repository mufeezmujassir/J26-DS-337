"""Offline repair for the Gate 5B listing-card description contamination."""
from __future__ import annotations

from pathlib import Path

from app.time_context.governance.multi_page_pilot import repair_listing_scope_contamination


def main() -> None:
    reports = Path("data/reports")
    repaired = repair_listing_scope_contamination(
        extraction_path=reports / "stage_10_1_3e_gate5b_extraction_results.json",
        completeness_path=reports / "stage_10_1_3e_gate5b_field_completeness.json",
        review_queue_path=reports / "stage_10_1_3e_gate5b_human_review_queue.json",
    )
    print(f"Repaired listing records: {repaired}")


if __name__ == "__main__":
    main()
