"""Offline-only Stage 12.3D.4 research evaluation helpers.

This module deliberately has no database write or recommendation-routing
behaviour.  It is used to prepare blinded human-review material and to score
already-labelled, fixed candidate universes.
"""
from __future__ import annotations

import hashlib
import math
import random
from collections import Counter, defaultdict
from statistics import median
from typing import Iterable


RELEVANCE_VALUES = {0, 1, 2, 3}
DEFAULT_CONTEXT_WEIGHTS = {
    "holiday": 0.20,
    "poya": 0.35,
    "verified_event": 0.25,
    "interests": 0.20,
}


# These are deliberately author-authored research scenarios, not observations
# of actual tourists.  Dates include Poya, ordinary, event, and missing-data
# cases while retaining stable identifiers for a reproducible split.
QUERY_SPECS: list[dict] = [
    {"query_id": "d4_01_galle_heritage_poya", "travel_date": "2026-01-03", "interests": ["heritage", "culture", "walking"], "district_ids": [78], "scenario_group": "heritage", "context_expectation": "poya"},
    {"query_id": "d4_02_kandy_religious_poya", "travel_date": "2026-02-01", "interests": ["religious", "heritage", "culture"], "district_ids": [], "scenario_group": "religious", "context_expectation": "poya"},
    {"query_id": "d4_03_anuradhapura_poya", "travel_date": "2026-03-02", "interests": ["buddhist", "heritage"], "district_ids": [], "scenario_group": "religious", "context_expectation": "poya"},
    {"query_id": "d4_04_colombo_event_date", "travel_date": "2026-10-01", "interests": ["art", "culture", "exhibition"], "district_ids": [], "scenario_group": "event", "context_expectation": "event_unverified_location"},
    {"query_id": "d4_05_yala_wildlife", "travel_date": "2026-10-20", "interests": ["wildlife", "safari", "nature"], "district_ids": [], "scenario_group": "wildlife", "context_expectation": "ordinary_day"},
    {"query_id": "d4_06_mirissa_beach", "travel_date": "2026-10-20", "interests": ["beach", "coastal", "relaxation"], "district_ids": [], "scenario_group": "beach", "context_expectation": "ordinary_day"},
    {"query_id": "d4_07_ella_hiking", "travel_date": "2026-10-20", "interests": ["hiking", "nature", "scenic"], "district_ids": [], "scenario_group": "nature", "context_expectation": "ordinary_day"},
    {"query_id": "d4_08_sigiriya_family", "travel_date": "2026-10-20", "interests": ["heritage", "family", "history"], "district_ids": [], "scenario_group": "family", "context_expectation": "ordinary_day"},
    {"query_id": "d4_09_galle_family", "travel_date": "2026-10-20", "interests": ["family", "heritage", "walking"], "district_ids": [78], "scenario_group": "family", "context_expectation": "ordinary_day"},
    {"query_id": "d4_10_trincomalee_coast", "travel_date": "2026-10-20", "interests": ["beach", "snorkelling", "coastal"], "district_ids": [], "scenario_group": "beach", "context_expectation": "ordinary_day"},
    {"query_id": "d4_11_sinharaja_nature", "travel_date": "2026-10-20", "interests": ["nature", "rainforest", "wildlife"], "district_ids": [], "scenario_group": "nature", "context_expectation": "ordinary_day"},
    {"query_id": "d4_12_dambulla_culture", "travel_date": "2026-10-20", "interests": ["culture", "temple", "heritage"], "district_ids": [], "scenario_group": "heritage", "context_expectation": "ordinary_day"},
    {"query_id": "d4_13_nuwara_eliya_family", "travel_date": "2026-10-20", "interests": ["family", "nature", "scenic"], "district_ids": [], "scenario_group": "family", "context_expectation": "ordinary_day"},
    {"query_id": "d4_14_arugam_bay_surf", "travel_date": "2026-10-20", "interests": ["beach", "surfing", "adventure"], "district_ids": [], "scenario_group": "beach", "context_expectation": "ordinary_day"},
    {"query_id": "d4_15_polonnaruwa_history", "travel_date": "2026-10-20", "interests": ["history", "archaeology", "heritage"], "district_ids": [], "scenario_group": "heritage", "context_expectation": "ordinary_day"},
    {"query_id": "d4_16_horton_plains", "travel_date": "2026-10-20", "interests": ["hiking", "nature", "wildlife"], "district_ids": [], "scenario_group": "nature", "context_expectation": "ordinary_day"},
    {"query_id": "d4_17_jaffna_culture", "travel_date": "2026-10-20", "interests": ["culture", "heritage", "food"], "district_ids": [], "scenario_group": "cultural", "context_expectation": "ordinary_day"},
    {"query_id": "d4_18_bentota_family", "travel_date": "2026-10-20", "interests": ["family", "beach", "water"], "district_ids": [], "scenario_group": "family", "context_expectation": "ordinary_day"},
    {"query_id": "d4_19_kataragama_religious", "travel_date": "2026-10-20", "interests": ["religious", "culture", "pilgrimage"], "district_ids": [], "scenario_group": "religious", "context_expectation": "ordinary_day"},
    {"query_id": "d4_20_udawalawe_safari", "travel_date": "2026-10-20", "interests": ["wildlife", "safari", "family"], "district_ids": [], "scenario_group": "wildlife", "context_expectation": "ordinary_day"},
    {"query_id": "d4_21_negombo_coast", "travel_date": "2026-10-20", "interests": ["beach", "food", "culture"], "district_ids": [], "scenario_group": "beach", "context_expectation": "ordinary_day"},
    {"query_id": "d4_22_knuckles_hiking", "travel_date": "2026-10-20", "interests": ["hiking", "adventure", "nature"], "district_ids": [], "scenario_group": "nature", "context_expectation": "ordinary_day"},
    {"query_id": "d4_23_galle_photography", "travel_date": "2026-10-20", "interests": ["heritage", "photography", "walking"], "district_ids": [78], "scenario_group": "heritage", "context_expectation": "ordinary_day"},
    {"query_id": "d4_24_cultural_triangle", "travel_date": "2026-10-20", "interests": ["heritage", "archaeology", "culture"], "district_ids": [], "scenario_group": "heritage", "context_expectation": "ordinary_day"},
    {"query_id": "d4_25_birdwatching", "travel_date": "2026-10-20", "interests": ["wildlife", "nature", "birdwatching"], "district_ids": [], "scenario_group": "wildlife", "context_expectation": "ordinary_day"},
    {"query_id": "d4_26_colombo_museum", "travel_date": "2026-10-20", "interests": ["museum", "history", "culture"], "district_ids": [], "scenario_group": "cultural", "context_expectation": "ordinary_day"},
    {"query_id": "d4_27_ordinary_unknown_context", "travel_date": "2027-12-31", "interests": ["nature", "culture"], "district_ids": [], "scenario_group": "missing_context", "context_expectation": "no_stored_calendar_evidence"},
    {"query_id": "d4_28_future_holiday_unknown", "travel_date": "2028-01-01", "interests": ["family", "heritage"], "district_ids": [], "scenario_group": "missing_context", "context_expectation": "no_stored_calendar_evidence"},
    {"query_id": "d4_29_anuradhapura_ordinary", "travel_date": "2026-10-20", "interests": ["religious", "heritage", "walking"], "district_ids": [], "scenario_group": "religious", "context_expectation": "ordinary_day"},
    {"query_id": "d4_30_wilpattu_wildlife", "travel_date": "2026-10-20", "interests": ["wildlife", "safari", "nature"], "district_ids": [], "scenario_group": "wildlife", "context_expectation": "ordinary_day"},
    {"query_id": "d4_31_south_coast_relax", "travel_date": "2026-10-20", "interests": ["beach", "relaxation", "family"], "district_ids": [], "scenario_group": "beach", "context_expectation": "ordinary_day"},
    {"query_id": "d4_32_kandy_culture", "travel_date": "2026-10-20", "interests": ["culture", "heritage", "religious"], "district_ids": [], "scenario_group": "cultural", "context_expectation": "ordinary_day"},
]


def presentation_key(query_id: str, attraction_id: int, seed: int = 12345) -> str:
    return hashlib.sha256(f"stage12_3d4:{seed}:{query_id}:{attraction_id}".encode()).hexdigest()


def deterministic_split(specs: Iterable[dict], seed: int = 12345, development_fraction: float = 0.70) -> dict[str, str]:
    """Split by scenario group, preventing group-level leakage.

    Each group is assigned as a unit via a stable hash; the small query set is
    therefore repeatable and no near-duplicate group crosses the split.
    """
    groups = sorted({str(item["scenario_group"]) for item in specs})
    rng = random.Random(seed)
    rng.shuffle(groups)
    cutoff = max(1, min(len(groups) - 1, round(len(groups) * development_fraction)))
    development = set(groups[:cutoff])
    return {item["query_id"]: ("development" if item["scenario_group"] in development else "held_out") for item in specs}


def validate_human_annotations(rows: Iterable[dict], known_pairs: set[tuple[str, str]]) -> dict:
    valid, invalid, missing, duplicate = [], [], [], []
    seen: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        reviewer = str(row.get("reviewer_id", "")).strip()
        query_id = str(row.get("query_id", "")).strip()
        attraction_id = str(row.get("attraction_id", "")).strip()
        key = (reviewer, query_id, attraction_id)
        if not all(key) or (query_id, attraction_id) not in known_pairs:
            invalid.append({"row": row_number, "reason": "unknown_or_missing_annotation_identity"}); continue
        if key in seen:
            duplicate.append({"row": row_number, "identity": key}); continue
        seen.add(key)
        raw = str(row.get("relevance_0_to_3", "")).strip()
        cannot_judge = str(row.get("cannot_judge", "")).casefold() in {"true", "1", "yes"}
        if cannot_judge:
            valid.append({**row, "cannot_judge": True, "relevance_0_to_3": None}); continue
        if raw == "":
            missing.append({"row": row_number, "identity": key}); continue
        try:
            value = int(raw)
        except ValueError:
            invalid.append({"row": row_number, "reason": "label_not_integer"}); continue
        if value not in RELEVANCE_VALUES:
            invalid.append({"row": row_number, "reason": "label_outside_0_to_3"}); continue
        valid.append({**row, "cannot_judge": False, "relevance_0_to_3": value})
    return {"valid": valid, "invalid": invalid, "missing": missing, "duplicates": duplicate}


def weighted_kappa(rows: Iterable[dict], first: str, second: str) -> float | None:
    pairs: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for row in rows:
        if not row.get("cannot_judge") and row["reviewer_id"] in {first, second}:
            pairs[(str(row["query_id"]), str(row["attraction_id"]))][str(row["reviewer_id"])] = int(row["relevance_0_to_3"])
    comparable = [pair for pair in pairs.values() if set(pair) == {first, second}]
    if len(comparable) < 2:
        return None
    matrix = [[0 for _ in range(4)] for _ in range(4)]
    for pair in comparable: matrix[pair[first]][pair[second]] += 1
    total = len(comparable)
    row_totals = [sum(row) for row in matrix]
    col_totals = [sum(matrix[row][col] for row in range(4)) for col in range(4)]
    weight = lambda a, b: ((a - b) / 3) ** 2
    observed = sum(weight(a, b) * matrix[a][b] / total for a in range(4) for b in range(4))
    expected = sum(weight(a, b) * row_totals[a] * col_totals[b] / (total * total) for a in range(4) for b in range(4))
    return None if expected == 0 else round(1 - observed / expected, 6)


def combined_score(baseline_score: float, context_score: float | None, context_weight: float = 0.20) -> float:
    """Keep unavailable context neutral by retaining the baseline unchanged."""
    if context_score is None:
        return baseline_score
    return round((1 - context_weight) * baseline_score + context_weight * context_score, 6)


def candidate_weight_grid(step: float = 0.25) -> list[dict[str, float]]:
    """Return a deterministic simplex grid for development-only calibration.

    This generator does not select a winner; callers must score candidates on
    development groups only, freeze the selected weights, and then evaluate on
    the held-out groups.  A coarse default avoids a misleading claim of
    precision on a small research data set.
    """
    units = round(1 / step)
    if units <= 0 or abs(units * step - 1) > 1e-9:
        raise ValueError("step must divide 1 exactly")
    values: list[dict[str, float]] = []
    for holiday in range(units + 1):
        for poya in range(units - holiday + 1):
            for event in range(units - holiday - poya + 1):
                interests = units - holiday - poya - event
                values.append({"holiday": holiday / units, "poya": poya / units, "verified_event": event / units, "interests": interests / units})
    return values


def context_score_for_weights(components: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Re-normalize only evidence eligible for a record.

    The caller supplies only the Stage 12.3D.3 eligible components.  Therefore
    Poya/holiday dependency and candidate-event exclusion remain enforced by
    the scoring service rather than being reintroduced during calibration.
    """
    eligible = {name: value for name, value in components.items() if value is not None and weights.get(name, 0) > 0}
    denominator = sum(weights[name] for name in eligible)
    return None if denominator == 0 else round(sum(weights[name] * value for name, value in eligible.items()) / denominator, 6)


def select_development_weights(rows: list[dict], labels: dict[tuple[str, str], int], split: dict[str, str], step: float = 0.25) -> dict:
    """Choose a coarse grid candidate exclusively from development queries."""
    development = [row for row in rows if split.get(row["query_id"]) == "development"]
    if not development or not labels:
        return {"selected": None, "reason": "development_labels_unavailable", "candidates_evaluated": 0}
    results = []
    for weights in candidate_weight_grid(step):
        by_query: dict[str, list[dict]] = defaultdict(list)
        for row in development: by_query[row["query_id"]].append(row)
        query_scores = []
        for query_id, query_rows in by_query.items():
            relevant = {str(row["attraction_id"]): labels[(query_id, str(row["attraction_id"]))] for row in query_rows if (query_id, str(row["attraction_id"])) in labels}
            if not relevant: continue
            ranked = sorted(query_rows, key=lambda row: (-combined_score(row["baseline_score"], context_score_for_weights(row.get("context_components", {}), weights)), row["attraction_id"]))
            value = ranking_metrics([str(row["attraction_id"]) for row in ranked], relevant, 5)["ndcg_at_5"]
            if value is not None: query_scores.append(value)
        results.append({"weights": weights, "development_mean_ndcg_at_5": None if not query_scores else round(sum(query_scores) / len(query_scores), 6), "development_queries": len(query_scores)})
    usable = [row for row in results if row["development_mean_ndcg_at_5"] is not None]
    return {"selected": None if not usable else sorted(usable, key=lambda row: (-row["development_mean_ndcg_at_5"], str(row["weights"])))[0], "candidates_evaluated": len(results), "all_candidates": results}


def ranking_metrics(ranked_ids: list[str], labels: dict[str, int], cutoff: int) -> dict:
    judged = [item for item in ranked_ids if item in labels]
    grades = [labels[item] for item in judged]
    at_k = grades[:cutoff]
    ideal = sorted(labels.values(), reverse=True)[:cutoff]
    dcg = lambda values: sum((2 ** grade - 1) / math.log2(index + 2) for index, grade in enumerate(values))
    relevant = sum(score >= 2 for score in at_k)
    total_relevant = sum(score >= 2 for score in labels.values())
    first = next((index + 1 for index, score in enumerate(at_k) if score >= 2), None)
    return {
        f"ndcg_at_{cutoff}": None if not ideal or dcg(ideal) == 0 else round(dcg(at_k) / dcg(ideal), 6),
        f"precision_at_{cutoff}": None if not at_k else round(relevant / len(at_k), 6),
        f"judged_pool_recall_at_{cutoff}": None if total_relevant == 0 else round(relevant / total_relevant, 6),
        f"mrr_at_{cutoff}": None if first is None else round(1 / first, 6),
        "judged_candidates_in_ranked_list": len(judged),
        "unjudged_candidates_in_ranked_list": len(ranked_ids) - len(judged),
        "recall_scope": "judged_candidate_pool_only",
    }


def latency_summary(milliseconds: Iterable[float]) -> dict:
    values = sorted(milliseconds)
    if not values: return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None}
    return {"count": len(values), "mean_ms": round(sum(values) / len(values), 3), "median_ms": round(median(values), 3), "p95_ms": round(values[max(0, math.ceil(.95 * len(values)) - 1)], 3)}
