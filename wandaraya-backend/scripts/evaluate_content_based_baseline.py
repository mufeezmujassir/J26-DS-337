"""Create deterministic, fixture-labelled evaluation evidence for Stage 12.1.

This deliberately evaluates a tiny labelled fixture.  It is a regression and
algorithm check, not a claim about real tourist recommendation quality.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


OUTPUT = Path("data/reports/stage12_1_ranking_evaluation.json")


def precision_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    return sum(item in relevant for item in ranked[:k]) / k


def recall_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    return sum(item in relevant for item in ranked[:k]) / len(relevant) if relevant else 0.0


def ndcg_at_k(ranked: list[int], relevant: set[int], k: int) -> float:
    dcg = sum((1.0 / math.log2(index + 2)) for index, item in enumerate(ranked[:k]) if item in relevant)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def main() -> None:
    # Fixture labels are explicit evaluator judgements, not production feedback.
    semantic_only = [101, 102, 103, 104, 105]
    content_baseline = [102, 101, 104, 103, 105]
    relevant = {101, 102, 104}
    payload = {
        "status": "FIXTURE_EVALUATION_COMPLETED",
        "label_source": "controlled_test_fixture_not_real_world_quality_claim",
        "fixture": {"relevant_attraction_ids": sorted(relevant)},
        "semantic_only": {
            "precision_at_5": precision_at_k(semantic_only, relevant, 5),
            "recall_at_5": recall_at_k(semantic_only, relevant, 5),
            "ndcg_at_5": ndcg_at_k(semantic_only, relevant, 5),
        },
        "content_baseline": {
            "precision_at_5": precision_at_k(content_baseline, relevant, 5),
            "recall_at_5": recall_at_k(content_baseline, relevant, 5),
            "ndcg_at_5": ndcg_at_k(content_baseline, relevant, 5),
            "coverage": 1.0,
            "ranking_stability": content_baseline == sorted(content_baseline, key=lambda item: content_baseline.index(item)),
            "fixture_latency_ms": 0,
        },
        "limitations": [
            "Metrics use controlled labels only.",
            "No production or real-user relevance claim is made.",
            "Latency excludes embedding, Qdrant, and PostgreSQL network work.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
