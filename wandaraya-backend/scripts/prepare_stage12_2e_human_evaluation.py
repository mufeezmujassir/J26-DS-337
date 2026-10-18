"""Create Stage 12.2E reviewer templates from the existing Stage 12.2D pool."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path("data/reports")
QUERIES = [
    ("q01_galle_heritage", "heritage attractions and walking in Galle", "district=78; category=Heritage; activity=Walking", "Heritage walk with geographic preference."),
    ("q02_southern_beaches", "beaches in Southern Province", "region=Southern Province; category=Beach", "Coastal leisure."),
    ("q03_wildlife_safari", "wildlife safaris in Sri Lanka", "category=Wildlife; activity=Safari", "Wildlife viewing."),
    ("q04_cultural_religious", "cultural and religious attractions", "category=Culture/Religion", "Temples and cultural heritage."),
    ("q05_hiking_adventure", "hiking and adventure activities", "activity=Hiking/Adventure", "Outdoor physical activity."),
    ("q06_family", "family friendly attractions", "travel_style=family", "Suitable for a mixed-age group."),
    ("q07_hill_country", "hill-country nature attractions", "region=Central/Uva", "Nature and scenic travel."),
    ("q08_archaeology", "historical and archaeological sites", "category=History & Archaeology", "Historic sites."),
    ("q09_culinary", "food and culinary tourism", "activity=Food/Culinary", "Food experiences."),
    ("q10_photography", "photography and scenic attractions", "category=Photography & Scenic Spots", "Visual/scenic travel."),
]


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "stage12_2e_query_set.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output); writer.writerow(["query_id", "query_text", "constraints", "expected_intent_note"]); writer.writerows(QUERIES)
    source = ROOT / "stage12_2d_human_relevance_workbook.csv"
    rows = list(csv.DictReader(source.open(encoding="utf-8", newline="")))
    fields = ["reviewer_id", "query_id", "query", "attraction_id", "attraction_name", "baseline_rank", "experimental_rank", "relevance_0_to_3", "reviewer_notes"]
    for reviewer in ("R1", "R2"):
        with (ROOT / f"stage12_2e_reviewer_{'1' if reviewer == 'R1' else '2'}_template.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
            for row in rows:
                writer.writerow({"reviewer_id": reviewer, "query_id": "q01_galle_heritage", "query": row["query"], "attraction_id": row["attraction_id"], "attraction_name": row["attraction_name"], "baseline_rank": row["baseline_rank"], "experimental_rank": row["experimental_rank"], "relevance_0_to_3": "", "reviewer_notes": ""})
    (ROOT / "stage12_2e_annotation_guidelines.md").write_text("""# Stage 12.2E relevance annotation\n\nScore each candidate independently for the stated tourist query.\n\n- **0 — Irrelevant:** not a plausible answer.\n- **1 — Weakly relevant:** related but a poor fit for interest, location, category, activity, or suitability.\n- **2 — Relevant:** a reasonable recommendation.\n- **3 — Highly relevant:** an excellent direct match.\n\nDo not infer missing facts. Consider interests, geography, requested categories and activities, and actual tourist suitability. Reviewers R1 and R2 must score independently. Leave a score blank if unsure; do not copy another reviewer. Disagreements require a separate adjudication decision and notes.\n""", encoding="utf-8")
    summary = {"status": "AWAITING_HUMAN_RELEVANCE_LABELS", "queries_defined": len(QUERIES), "candidate_pool_available_for_annotation": len(rows), "reviewers": ["R1", "R2"], "production_ranking_policy_changed": False, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0}
    for filename in ("stage12_2e_label_quality.json", "stage12_2e_ranking_metrics.json", "stage12_2e_final_summary.json"):
        (ROOT / filename).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (ROOT / "stage12_2e_comparison_report.md").write_text("# Stage 12.2E comparison\n\nMetrics are intentionally unavailable until two independent reviewers provide genuine labels. Any later recall metric will be explicitly judged-pool recall unless all relevant attractions in the candidate universe have been assessed.\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
