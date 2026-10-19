"""Deterministic metrics and validation for manually supplied relevance data."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def validate_annotations(rows: Iterable[dict]) -> dict:
    seen: set[tuple[str, str, str]] = set()
    duplicates, invalid, missing = [], [], []
    valid = []
    for index, row in enumerate(rows, start=2):
        key = (str(row.get("reviewer_id", "")), str(row.get("query_id", "")), str(row.get("attraction_id", "")))
        if not all(key):
            invalid.append({"row": index, "reason": "missing_stable_identifier"})
            continue
        if key in seen:
            duplicates.append({"row": index, "key": key})
            continue
        seen.add(key)
        raw = str(row.get("relevance_0_to_3", row.get("reviewer_relevance_0_to_3", ""))).strip()
        if not raw:
            missing.append({"row": index, "key": key})
            continue
        try:
            relevance = int(raw)
        except ValueError:
            invalid.append({"row": index, "key": key, "reason": "relevance_not_integer"})
            continue
        if relevance not in (0, 1, 2, 3):
            invalid.append({"row": index, "key": key, "reason": "relevance_outside_0_to_3"})
            continue
        valid.append({**row, "relevance_0_to_3": relevance})
    return {"valid": valid, "duplicates": duplicates, "invalid": invalid, "missing": missing}


def disagreement_report(valid_rows: Iterable[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in valid_rows:
        grouped[(str(row["query_id"]), str(row["attraction_id"]))].append(row)
    findings = []
    for (query_id, attraction_id), rows in sorted(grouped.items()):
        if len(rows) < 2 or len({row["relevance_0_to_3"] for row in rows}) <= 1:
            continue
        findings.append({"query_id": query_id, "attraction_id": attraction_id, "reviewer_scores": {str(row["reviewer_id"]): row["relevance_0_to_3"] for row in rows}, "requires_adjudication": True})
    return findings


def _dcg(grades: list[int], k: int) -> float:
    return sum((2 ** grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades[:k]))


def ranking_metrics(ranked_ids: list[str], labels: dict[str, int], k: int) -> dict:
    judged = [attraction_id for attraction_id in ranked_ids if attraction_id in labels]
    grades = [labels[attraction_id] for attraction_id in judged]
    denominator = min(k, len(judged))
    binary_relevant = sum(grade >= 2 for grade in grades[:k])
    judged_relevant_total = sum(grade >= 2 for grade in labels.values())
    ideal = sorted(labels.values(), reverse=True)
    first_relevant = next((index + 1 for index, grade in enumerate(grades[:k]) if grade >= 2), None)
    return {
        f"precision_at_{k}": None if denominator == 0 else binary_relevant / denominator,
        f"judged_pool_recall_at_{k}": None if judged_relevant_total == 0 else binary_relevant / judged_relevant_total,
        f"ndcg_at_{k}": None if _dcg(ideal, k) == 0 else _dcg(grades, k) / _dcg(ideal, k),
        f"mrr_at_{k}": None if first_relevant is None else 1 / first_relevant,
        "judged_candidates_in_ranked_list": len(judged),
        "recall_denominator": "judged_pool_only_not_global_relevance",
    }
