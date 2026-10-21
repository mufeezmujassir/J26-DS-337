"""Run Stage 12.5 R0-R3 diagnostics without claiming ranking accuracy.

This uses real semantic retrieval and repository evidence.  It deliberately
does not compute relevance metrics unless future independent recommendation
labels are supplied under a separately reviewed protocol.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.database import AsyncSessionLocal
from app.recommendation.unified_context.orchestrator import UnifiedContextOrchestrator
from app.recommendation.unified_context.schemas import RerankerConfiguration, UnifiedContextRequest


async def run(args) -> dict:
    base = dict(
        query=args.query,
        travel_datetime=datetime.fromisoformat(args.travel_datetime),
        activity_type_id=args.activity_type_id,
        requested_activities=[args.activity] if args.activity else [],
        interests=args.interests,
        limit=args.limit,
        candidate_pool_size=max(args.limit, args.candidate_pool_size),
    )
    runs = {}
    async with AsyncSessionLocal() as db:
        service = UnifiedContextOrchestrator(db, engine_enabled=True, reranking_enabled=True)
        for configuration in RerankerConfiguration:
            result = await service.recommend(UnifiedContextRequest(**base, configuration=configuration))
            runs[configuration.value] = result.model_dump(mode="json")
    return {
        "stage": "12.5",
        "version": "stage12_5_unified_context_v1",
        "evaluation_type": "engineering_diagnostics_and_future_blinded_review_package",
        "recommendation_accuracy_status": "UNIFIED_RANKING_ACCURACY_NOT_YET_VALIDATED",
        "accuracy_metrics": None,
        "metric_limitation": "No independent five-layer attraction-relevance judgments were supplied; NDCG, Precision@5, and MRR were not fabricated.",
        "configurations": runs,
        "blinded_review_items": [
            {
                "query": args.query,
                "travel_datetime": args.travel_datetime,
                "configuration_orders": {name: value["experimental_candidate_order"] for name, value in runs.items()},
                "independent_relevance_judgments": [],
                "review_status": "PENDING_INDEPENDENT_REVIEW",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--travel-datetime", required=True, help="ISO-8601 timestamp with timezone")
    parser.add_argument("--activity-type-id", type=int)
    parser.add_argument("--activity")
    parser.add_argument("--interests", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--candidate-pool-size", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("data/reports/stage12_5_reranker_comparison.json"))
    args = parser.parse_args()
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": payload["recommendation_accuracy_status"]}))


if __name__ == "__main__":
    main()
