"""Frozen Stage 12.4G prospective protocol and deterministic sampling helpers."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter

PROTOCOL_VERSION = "stage12_4g_prospective_protocol_v1"
DATASET_VERSION = "stage12_4g_prospective_review_v1"
SAMPLING_SEED = "wandaraya-stage12.4g-prospective-v1-20261021"
BOOTSTRAP_SEED = 12404
BOOTSTRAP_ITERATIONS = 10_000
TARGET_QUERY_COUNT = 72
MIN_COMPLETE_QUERIES = 60
MIN_INDEPENDENT_CLUSTERS = 15
PRACTICAL_IMPROVEMENT = 0.01


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: dict) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def protocol(model_hashes: dict[str, str]) -> dict:
    body = {
        "protocol_version": PROTOCOL_VERSION,
        "dataset_version": DATASET_VERSION,
        "frozen_before_labels": True,
        "primary_question": "Does the frozen original activity-aware seasonality model improve monthly attraction-activity ranking over the frozen district multivariable reference on a new independently judged dataset?",
        "primary_metric": "mean_ndcg_at_5_complete_12_month_queries",
        "primary_candidate": {"identifier": "activity_aware", "version": "12.4d_v1", "configuration_hash": model_hashes["activity_aware"]},
        "primary_baseline": {"identifier": "district_multivariable", "version": "12.4c_v1", "configuration_hash": model_hashes["district_multivariable"]},
        "secondary_metrics": ["ndcg_at_3", "ndcg_at_12", "spearman_tie_aware", "kendall_tau_b", "top_3_overlap", "mrr_relevance_ge_3", "geographic_subgroups", "activity_subgroups", "missingness", "coverage"],
        "sampling": {"seed": SAMPLING_SEED, "target_queries": TARGET_QUERY_COUNT,
            "exclude_all_stage12_4e2_queries": True, "selection_uses_predictions": False,
            "months_per_query": 12, "reviewers_per_item": 2,
            "strata": ["climate_source_identity", "district", "activity_family", "mapping_evidence_tier", "geographic_evidence_level"]},
        "analysis": {"paired_unit": "complete_attraction_activity_query", "cluster_unit": "climate_source_identity",
            "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "confidence_interval": "two-sided cluster bootstrap percentile 95%",
            "ties": "deterministic month-number tie break for ranked lists; average ranks for Spearman; Kendall tau-b tie correction",
            "incomplete_rankings": "excluded from full-ranking metrics", "insufficient_evidence": "missing_not_zero",
            "secondary_multiplicity": "Holm-adjusted when inferential p-values are reported; otherwise descriptive and explicitly exploratory"},
        "decision_rule": {
            "minimum_complete_queries": MIN_COMPLETE_QUERIES,
            "minimum_independent_clusters": MIN_INDEPENDENT_CLUSTERS,
            "practical_mean_ndcg5_difference": PRACTICAL_IMPROVEMENT,
            "SUPPORTED_IMPROVEMENT": "minimum data met AND paired mean difference >= 0.01 AND cluster-bootstrap 95% lower bound > 0",
            "NO_ESTABLISHED_IMPROVEMENT": "minimum data met but supported-improvement rule is not met",
            "INSUFFICIENT_INDEPENDENT_EVIDENCE": "fewer than 60 complete queries OR fewer than 15 independent clusters OR incomplete verified adjudication",
        },
        "power_statement": "The target is feasibility-based; no guaranteed statistical power is claimed. Precision depends on realized labels and effective climate-source clusters.",
        "prohibited": ["retrospective_fixed_blend_as_primary", "stage12_4e2_query_overlap", "model_error_based_sampling", "automatic_disagreement_resolution"],
    }
    body["protocol_hash"] = sha256_json(body)
    return body


def stable_key(row: dict) -> str:
    token = f"{SAMPLING_SEED}|{row['attraction_id']}|{row['activity_type_id']}"
    return hashlib.sha256(token.encode()).hexdigest()


def deterministic_sample(inventory: list[dict], target: int = TARGET_QUERY_COUNT) -> list[dict]:
    """Prediction-blind diversity sampling with deterministic hash tie-breaks."""
    if target <= 0:
        return []
    rows = sorted(inventory, key=stable_key)
    selected, used = [], set()

    def add_first(group_key, values=None):
        groups = sorted({group_key(r) for r in rows} if values is None else values, key=str)
        for group in groups:
            candidate = next((r for r in rows if group_key(r) == group and (r["attraction_id"], r["activity_type_id"]) not in used), None)
            if candidate and len(selected) < target:
                selected.append(candidate); used.add((candidate["attraction_id"], candidate["activity_type_id"]))

    # Preserve scarce coordinate evidence first, then all observed strata.
    for row in rows:
        if row["geographic_evidence_level"] == "ATTRACTION_COORDINATE_REANALYSIS" and len(selected) < target:
            selected.append(row); used.add((row["attraction_id"], row["activity_type_id"]))
    add_first(lambda r: r["district"])
    add_first(lambda r: r["activity_type_id"])
    add_first(lambda r: r["mapping_evidence_tier"] or "NONE")

    cluster_counts = Counter(r["climate_source_identity"] for r in selected)
    activity_counts = Counter(r["activity_type_id"] for r in selected)
    remaining = [r for r in rows if (r["attraction_id"], r["activity_type_id"]) not in used]
    while remaining and len(selected) < target:
        remaining.sort(key=lambda r: (cluster_counts[r["climate_source_identity"]], activity_counts[r["activity_type_id"]], stable_key(r)))
        row = remaining.pop(0)
        selected.append(row); used.add((row["attraction_id"], row["activity_type_id"]))
        cluster_counts[row["climate_source_identity"]] += 1
        activity_counts[row["activity_type_id"]] += 1
    return selected


def month_order(scores: dict[int, float]) -> list[int]:
    return sorted(scores, key=lambda month: (-scores[month], month))


def cluster_bootstrap(differences: dict[str, list[float]], *, seed: int = BOOTSTRAP_SEED,
                      iterations: int = BOOTSTRAP_ITERATIONS) -> dict:
    keys = sorted(differences)
    if not keys:
        return {"status": "NO_DATA", "clusters": 0}
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample = [rng.choice(keys) for _ in keys]
        values = [value for key in sample for value in differences[key]]
        estimates.append(sum(values) / len(values))
    estimates.sort()
    return {"status": "COMPUTED", "clusters": len(keys), "iterations": iterations, "seed": seed,
            "mean": sum(estimates) / len(estimates),
            "ci95": [estimates[int(.025 * iterations)], estimates[min(iterations - 1, int(.975 * iterations))]]}
