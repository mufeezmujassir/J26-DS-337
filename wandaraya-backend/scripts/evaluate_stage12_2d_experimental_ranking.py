"""Produce a human-reviewable, read-only Stage 12.2D ranking comparison."""
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


REPORT_ROOT = Path("data/reports")
QUERY = "heritage attractions and walking in Galle"


async def main() -> None:
    request = ContentBasedRecommendationRequest(interests=QUERY, preferred_district_ids=[78], preferred_categories=["Heritage"], preferred_activities=["Walking"], limit=20, candidate_pool_size=30)
    async with AsyncSessionLocal() as db:
        service = ContentBasedRecommendationService(db)
        query = service.build_retrieval_query(request)
        candidates = service._deduplicate_candidates(await service.retriever.search(db, query, 30))
        records = await service._hydrate([candidate.attraction_id for candidate in candidates])
        baseline = [service._score_candidate(request, candidate, records[candidate.attraction_id]) for candidate in candidates if candidate.attraction_id in records]
        baseline.sort(key=lambda item: (-item.baseline_score, item.attraction_id))
        experimental = experimental_order(baseline, records)
    now = datetime.now(timezone.utc).isoformat()
    rows = [{
        "attraction_id": row["item"].attraction_id, "name": row["item"].attraction_name,
        "baseline_score": row["item"].baseline_score, "eligibility_bucket": row["eligibility_bucket"],
        "eligibility_review_flags": row["eligibility_review_flags"],
        "category_match_score": row["item"].category_match_score, "activity_match_score": row["item"].activity_match_score,
        "district_match_score": row["item"].district_match_score,
    } for row in experimental]
    labels_path = REPORT_ROOT / "stage12_2d_human_relevance_workbook.csv"
    with labels_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["query_id", "query", "attraction_id", "attraction_name", "baseline_rank", "experimental_rank", "reviewer_relevance_0_to_3", "reviewer_notes"])
        writer.writeheader()
        baseline_ranks = {item.attraction_id: index + 1 for index, item in enumerate(baseline)}
        for index, row in enumerate(rows, start=1):
            writer.writerow({"query_id": "galle_heritage_001", "query": QUERY, "attraction_id": row["attraction_id"], "attraction_name": row["name"], "baseline_rank": baseline_ranks[row["attraction_id"]], "experimental_rank": index, "reviewer_relevance_0_to_3": "", "reviewer_notes": ""})
    comparison = {"generated_at_utc": now, "policy_version": POLICY_VERSION, "query": QUERY, "baseline_top5": [{"id": item.attraction_id, "name": item.attraction_name, "score": item.baseline_score} for item in baseline[:5]], "experimental_top5": rows[:5], "production_policy_changed": False, "score_mutation": False, "method": "Ordering buckets: verified positive preference evidence, then partial/unknown evidence, then name-based eligibility-review records."}
    evaluation = {"status": "AWAITING_HUMAN_RELEVANCE_LABELS", "workbook": str(labels_path), "metrics_after_labels": ["Precision@5", "Recall@5", "NDCG@5", "ranking stability"], "no_real_world_accuracy_claim": True}
    summary = {"status": "EXPERIMENTAL_RANKING_TESTED", "policy_version": POLICY_VERSION, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0, "production_ranking_policy_changed": False, "human_review_required_before_proposal": True}
    for filename, body in {"stage12_2d_ranking_experiment.json": comparison, "stage12_2d_research_evaluation_plan.json": evaluation, "stage12_2d_final_summary.json": summary}.items():
        (REPORT_ROOT / filename).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
