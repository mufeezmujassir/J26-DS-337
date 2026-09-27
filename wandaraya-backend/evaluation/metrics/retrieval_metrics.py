from __future__ import annotations
import math
def precision_et_k(
        retrieved_ids:list[int],
        relevant_ids:list[int],
        k:int
)->float:
    if k<=0:
        raise ValueError("k must be greater than 0")
    top_k=retrieved_ids[:k]

    if not top_k:
        return 0.0

    relevant_retrieved = sum(
        1
        for attraction_id in top_k
        if attraction_id in relevant_ids
    )

    return relevant_retrieved / k

def recall_at_k(
    retrieved_ids: list[int],
    relevant_ids: set[int],
    k: int,
) -> float:
    """
    Recall@K = relevant_retrieved items / total_relevant

    """

    if k <= 0:
        raise ValueError("k must be greater than 0.")

    if not relevant_ids:
        return 0.0

    top_k = retrieved_ids[:k]

    relevant_retrieved = sum(
        1
        for attraction_id in top_k
        if attraction_id in relevant_ids
    )

    return (
        relevant_retrieved
        / len(relevant_ids)
    )


def reciprocal_rank(
    retrieved_ids: list[int],
    relevant_ids: set[int],
) -> float:
    """
    Reciprocal Rank.

    Returns:

        1 / rank of first relevant result

    1st->1.00 2nd 0.67.. something like
    """

    for rank, attraction_id in enumerate(
        retrieved_ids,
        start=1,
    ):

        if attraction_id in relevant_ids:

            return 1.0 / rank

    return 0.0


def dcg_at_k(
    retrieved_ids: list[int],
    relevant_ids: set[int],
    k: int,
) -> float:
    """
    Binary-relevance DCG@K.
    """

    if k <= 0:
        raise ValueError("k must be greater than 0.")

    score = 0.0

    for rank, attraction_id in enumerate(
        retrieved_ids[:k],
        start=1,
    ):

        relevance = (
            1.0
            if attraction_id in relevant_ids
            else 0.0
        )

        if relevance > 0:

            score += (
                relevance
                / math.log2(rank + 1)
            )

    return score


def ndcg_at_k(
    retrieved_ids: list[int],
    relevant_ids: set[int],
    k: int,
) -> float:
    """
    Normalized Discounted Cumulative Gain @ K.

    Current evaluation uses binary relevance:

        relevant     = 1
        not relevant = 0
    """

    if k <= 0:
        raise ValueError("k must be greater than 0.")

    if not relevant_ids:
        return 0.0

    actual_dcg = dcg_at_k(
        retrieved_ids,
        relevant_ids,
        k,
    )

    ideal_relevant_count = min(
        len(relevant_ids),
        k,
    )

    ideal_dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(
            1,
            ideal_relevant_count + 1,
        )
    )
    if ideal_dcg == 0:
        return 0.0

    return actual_dcg / ideal_dcg