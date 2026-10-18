"""Capture stable bounded candidate universes and blinded review templates."""
from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.database import AsyncSessionLocal
from app.recommendation.content_based.experimental_policy import POLICY_VERSION, experimental_order
from app.recommendation.content_based.schemas import ContentBasedRecommendationRequest
from app.recommendation.content_based.service import ContentBasedRecommendationService
from app.recommendation.evaluation.stage12_2f import QUERY_SPECS, blinded_order


ROOT = Path("data/reports")
POOL = 30


async def main() -> None:
    universe: list[dict] = []
    coverage: list[dict] = []
    async with AsyncSessionLocal() as db:
        service = ContentBasedRecommendationService(db)
        for spec in QUERY_SPECS:
            request = ContentBasedRecommendationRequest(interests=spec["query"], preferred_categories=spec["categories"], preferred_activities=spec["activities"], preferred_district_ids=spec["districts"], limit=20, candidate_pool_size=POOL)
            retrieval_query = service.build_retrieval_query(request)
            candidates = service._deduplicate_candidates(await service.retriever.search(db, retrieval_query, POOL))
            records = await service._hydrate([candidate.attraction_id for candidate in candidates])
            scored = [service._score_candidate(request, candidate, records[candidate.attraction_id]) for candidate in candidates if candidate.attraction_id in records]
            baseline = sorted(scored, key=lambda item: (-item.baseline_score, item.attraction_id))
            experimental = experimental_order(baseline, records)
            semantic_ranks = {candidate.attraction_id: index + 1 for index, candidate in enumerate(candidates)}
            baseline_ranks = {item.attraction_id: index + 1 for index, item in enumerate(baseline)}
            experimental_ranks = {row["item"].attraction_id: index + 1 for index, row in enumerate(experimental)}
            for candidate in candidates:
                record = records.get(candidate.attraction_id)
                if record is None:
                    continue
                universe.append({"query_id": spec["query_id"], "query": spec["query"], "attraction_id": candidate.attraction_id, "attraction_name": candidate.name, "district_id": record.attraction.district_id, "categories": list(record.category_names), "activities": list(record.activity_names), "semantic_rank": semantic_ranks[candidate.attraction_id], "baseline_rank": baseline_ranks[candidate.attraction_id], "experimental_rank": experimental_ranks[candidate.attraction_id], "experimental_eligibility_bucket": next(row["eligibility_bucket"] for row in experimental if row["item"].attraction_id == candidate.attraction_id), "blinded_order": blinded_order(spec["query_id"], candidate.attraction_id)})
            coverage.append({"query_id": spec["query_id"], "query": spec["query"], "candidate_pool_requested": POOL, "candidate_universe_count": len(candidates), "same_universe_across_semantic_baseline_experimental": True, "excluded_due_to_pool_limit": "unknown_without_unbounded_scan"})
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "stage12_2f_query_coverage.json").write_text(json.dumps({"queries": QUERY_SPECS, "coverage": coverage}, indent=2) + "\n", encoding="utf-8")
    (ROOT / "stage12_2f_candidate_universe.json").write_text(json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_pool_limit": POOL, "policy_versions": ["semantic_only", "content_baseline_v1", POLICY_VERSION], "records": universe, "postgresql_writes": False, "qdrant_writes": False}, indent=2) + "\n", encoding="utf-8")
    fields = ["annotation_batch_id", "reviewer_id", "query_id", "query", "attraction_id", "attraction_name", "district_id", "categories", "activities", "reviewer_relevance_0_to_3", "reviewer_notes"]
    for reviewer in ("R1", "R2"):
        path = ROOT / f"stage12_2f_reviewer_{'1' if reviewer == 'R1' else '2'}_template.csv"
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
            for row in sorted(universe, key=lambda item: (item["query_id"], item["blinded_order"])):
                writer.writerow({"annotation_batch_id": "stage12_2f_v1", "reviewer_id": reviewer, "query_id": row["query_id"], "query": row["query"], "attraction_id": row["attraction_id"], "attraction_name": row["attraction_name"], "district_id": row["district_id"], "categories": " | ".join(row["categories"]), "activities": " | ".join(row["activities"]), "reviewer_relevance_0_to_3": "", "reviewer_notes": ""})
    summary = {"status": "AWAITING_INDEPENDENT_HUMAN_LABELS", "queries_prepared": len(QUERY_SPECS), "candidate_rows_per_reviewer": len(universe), "blinded_templates": True, "production_ranking_policy_changed": False, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0}
    for filename in ("stage12_2f_annotation_integrity.json", "stage12_2f_per_query_metrics.json", "stage12_2f_macro_metrics.json", "stage12_2f_ranking_error_analysis.json", "stage12_2f_policy_decision.json", "stage12_2f_final_summary.json"):
        (ROOT / filename).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
