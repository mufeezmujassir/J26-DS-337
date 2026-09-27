from __future__ import annotations
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.knowledge_base.retrieval.semantic_retriever import SemanticAttractionRetriever

from evaluation.metrics.retrieval_metrics import(
    precision_et_k,
    recall_at_k,
    reciprocal_rank,
    ndcg_at_k
)

@dataclass
class QueryEvaluationResult:
    query_id:int
    query:str

    relevant_ids: list[int]
    retrieved_ids: list[int]

    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


@dataclass
class RetrievalEvaluationResult:
    k: int

    query_count: int = 0

    mean_precision_at_k: float = 0.0
    mean_recall_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    mean_ndcg_at_k: float = 0.0

    query_results: list[
        QueryEvaluationResult
    ] = field(
        default_factory=list
    )


class SemanticRetrievalEvaluator:
    def __init__(
            self,retriever:SemanticAttractionRetriever | None=None

    )->None:
        self.retriever = (
            retriever
            or SemanticAttractionRetriever()
        )

    async def evaluate(
        self,
        db: AsyncSession,
        dataset: list[dict],
        *,
        k: int = 5,
    ) -> RetrievalEvaluationResult:

        if k <= 0:
            raise ValueError(
                "k must be greater than 0."
            )

        evaluation = RetrievalEvaluationResult(
            k=k
        )

        precision_scores: list[float] = []
        recall_scores: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcg_scores: list[float] = []

        for item in dataset:

            query_id = str(
                item["id"]
            )

            query = str(
                item["query"]
            )

            relevant_ids = {
                int(attraction_id)
                for attraction_id
                in item[
                    "relevant_attraction_ids"
                ]
            }



            candidates = await self.retriever.search(
                db=db,
                query=query,
                limit=k,
            )

            retrieved_ids = [
                candidate.attraction_id
                for candidate in candidates
            ]


            precision = precision_et_k(
                retrieved_ids,
                relevant_ids,
                k,
            )

            recall = recall_at_k(
                retrieved_ids,
                relevant_ids,
                k,
            )

            rr = reciprocal_rank(
                retrieved_ids,
                relevant_ids,
            )

            ndcg = ndcg_at_k(
                retrieved_ids,
                relevant_ids,
                k,
            )

            precision_scores.append(
                precision
            )

            recall_scores.append(
                recall
            )

            reciprocal_ranks.append(
                rr
            )

            ndcg_scores.append(
                ndcg
            )

            evaluation.query_results.append(
                QueryEvaluationResult(
                    query_id=query_id,
                    query=query,
                    relevant_ids=sorted(
                        relevant_ids
                    ),
                    retrieved_ids=retrieved_ids,
                    precision_at_k=precision,
                    recall_at_k=recall,
                    reciprocal_rank=rr,
                    ndcg_at_k=ndcg,
                )
            )

        evaluation.query_count = len(
            evaluation.query_results
        )

        if evaluation.query_count == 0:
            return evaluation

        evaluation.mean_precision_at_k = (
            sum(precision_scores)
            / evaluation.query_count
        )

        evaluation.mean_recall_at_k = (
            sum(recall_scores)
            / evaluation.query_count
        )

        evaluation.mean_reciprocal_rank = (
            sum(reciprocal_ranks)
            / evaluation.query_count
        )

        evaluation.mean_ndcg_at_k = (
            sum(ndcg_scores)
            / evaluation.query_count
        )

        return evaluation
