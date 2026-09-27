from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.database import AsyncSessionLocal
from evaluation.retrieval_evaluator import SemanticRetrievalEvaluator

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_CANDIDATES = [
    BASE_DIR / "evaluation" / "dataset" / "retrieval_queries.json",
]
DATASET_PATH = next((path for path in DATASET_CANDIDATES if path.exists()), DATASET_CANDIDATES[0])
K = 5


def load_dataset() -> list[dict]:
    if not DATASET_PATH.exists():
        searched = ", ".join(str(path) for path in DATASET_CANDIDATES)
        raise FileNotFoundError(
            f"Semantic retrieval dataset not found. Looked in: {searched}"
        )

    with DATASET_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


async def main() -> None:
    print()
    print("=" * 70)
    print("WANDARAYA SEMANTIC RETRIEVAL EVALUATION")
    print("=" * 70)

    dataset = load_dataset()

    print(f"Evaluation queries: {len(dataset)}")
    print(f"K: {K}")

    async with AsyncSessionLocal() as db:
        evaluator = SemanticRetrievalEvaluator()
        result = await evaluator.evaluate(
            db=db,
            dataset=dataset,
            k=K,
        )

        for item in result.query_results:
            print()
            print("-" * 70)
            print(f"{item.query_id}: {item.query}")
            print(f"Relevant IDs:  {item.relevant_ids}")
            print(f"Retrieved IDs: {item.retrieved_ids}")
            print(f"Precision@{K}: {item.precision_at_k:.4f}")
            print(f"Recall@{K}:    {item.recall_at_k:.4f}")
            print(f"RR:            {item.reciprocal_rank:.4f}")
            print(f"NDCG@{K}:      {item.ndcg_at_k:.4f}")

        print()
        print("=" * 70)
        print("OVERALL RETRIEVAL METRICS")
        print("=" * 70)
        print(f"Queries:      {result.query_count}")
        print(f"Precision@{K}: {result.mean_precision_at_k:.4f}")
        print(f"Recall@{K}:    {result.mean_recall_at_k:.4f}")
        print(f"MRR:           {result.mean_reciprocal_rank:.4f}")
        print(f"NDCG@{K}:      {result.mean_ndcg_at_k:.4f}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())