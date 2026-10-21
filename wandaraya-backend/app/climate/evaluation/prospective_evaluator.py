"""Prospective evaluator with a hard genuine-label and protocol freeze gate."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from app.climate.evaluation.prospective import (DATASET_VERSION, MIN_COMPLETE_QUERIES,
    MIN_INDEPENDENT_CLUSTERS, PRACTICAL_IMPROVEMENT, cluster_bootstrap, sha256_json)
from app.climate.evaluation.ranking_metrics import ndcg, reciprocal_rank, top_k_overlap
from app.climate.evaluation.prospective import month_order
from scipy.stats import kendalltau, spearmanr

RELEVANCE = {"VERY_UNFAVORABLE": 0, "UNFAVORABLE": 1, "NEUTRAL": 2,
             "FAVORABLE": 3, "VERY_FAVORABLE": 4}


class ProspectiveEvaluationError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_protocol(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("protocol_hash", None)
    actual = sha256_json(value)
    value["protocol_hash"] = claimed
    if claimed != actual:
        raise ProspectiveEvaluationError("frozen protocol hash mismatch")
    return value


def pending_status(protocol_path: Path, submissions: list[Path], adjudications: Path | None = None) -> dict:
    protocol = validate_protocol(protocol_path)
    populated = 0
    reviewers = set()
    duplicates = set()
    seen = set()
    for path in submissions:
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if not row.get("decision", "").strip():
                    continue
                key = (row.get("review_item_id"), row.get("reviewer_id"))
                if key in seen:
                    duplicates.add(key)
                seen.add(key); populated += 1; reviewers.add(row.get("reviewer_id"))
    if duplicates:
        raise ProspectiveEvaluationError(f"duplicate prospective labels: {len(duplicates)}")
    adjudicated = 0
    if adjudications and adjudications.exists():
        with adjudications.open(encoding="utf-8-sig", newline="") as handle:
            adjudicated = sum(bool(r.get("final_decision", "").strip()) for r in csv.DictReader(handle))
    if populated == 0:
        return {"status": "PROSPECTIVE_VALIDATION_PENDING", "decision": "PENDING_INDEPENDENT_EVIDENCE",
                "protocol_version": protocol["protocol_version"], "protocol_hash_valid": True,
                "human_judgments": 0, "reviewer_count": 0, "adjudications": 0,
                "prospective_metrics": None, "statistical_significance": None, "model_approved": False}
    return {"status": "PROSPECTIVE_LABELS_INCOMPLETE", "decision": "PENDING_INDEPENDENT_EVIDENCE",
            "protocol_version": protocol["protocol_version"], "protocol_hash_valid": True,
            "human_judgments": populated, "reviewer_count": len(reviewers), "adjudications": adjudicated,
            "prospective_metrics": None, "model_approved": False}


def decision(mean_difference: float, lower_ci: float, complete_queries: int, clusters: int,
             adjudication_complete: bool) -> str:
    if complete_queries < MIN_COMPLETE_QUERIES or clusters < MIN_INDEPENDENT_CLUSTERS or not adjudication_complete:
        return "INSUFFICIENT_INDEPENDENT_EVIDENCE"
    if mean_difference >= PRACTICAL_IMPROVEMENT and lower_ci > 0:
        return "SUPPORTED_IMPROVEMENT"
    return "NO_ESTABLISHED_IMPROVEMENT"


def evaluate_verified_rows(rows: list[dict]) -> dict:
    """Evaluate already provenance-verified, adjudicated monthly rows."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["evaluation_query_id"]].append(row)
    complete = []
    for query_id, values in sorted(grouped.items()):
        numeric = [r for r in values if r.get("final_decision") in RELEVANCE]
        if len(numeric) != 12 or {int(r["calendar_month"]) for r in numeric} != set(range(1, 13)):
            continue
        rel = {int(r["calendar_month"]): RELEVANCE[r["final_decision"]] for r in numeric}
        activity_scores = {int(r["calendar_month"]): float(r["candidate_score"]) for r in numeric}
        baseline_scores = {int(r["calendar_month"]): float(r["baseline_score"]) for r in numeric}
        ideal = sorted(rel, key=lambda m: (-rel[m], m))
        candidate_order, baseline_order = month_order(activity_scores), month_order(baseline_scores)
        def metrics(order, scores):
            months=sorted(rel); x=[scores[m] for m in months]; y=[rel[m] for m in months]
            sp=float(spearmanr(x,y).statistic); kt=float(kendalltau(x,y,variant="b").statistic)
            return {"ndcg@3":ndcg(order,rel,3),"ndcg@5":ndcg(order,rel,5),"ndcg@12":ndcg(order,rel,12),
                "spearman":None if sp != sp else sp,"kendall_tau_b":None if kt != kt else kt,
                "top_3_overlap":top_k_overlap(order,ideal,3),
                "mrr_relevance_ge_3":reciprocal_rank(order,{m for m,v in rel.items() if v>=3})}
        cm,bm=metrics(candidate_order,activity_scores),metrics(baseline_order,baseline_scores)
        complete.append({"evaluation_query_id":query_id,"cluster":numeric[0]["climate_source_identity"],
            "activity_type":numeric[0].get("activity_type"),"geographic_evidence_level":numeric[0].get("geographic_evidence_level"),
            "candidate":cm,"baseline":bm,"ndcg5_difference":cm["ndcg@5"]-bm["ndcg@5"]})
    def aggregate(name):
        keys=["ndcg@3","ndcg@5","ndcg@12","spearman","kendall_tau_b","top_3_overlap","mrr_relevance_ge_3"]
        return {key:{"mean":sum(v)/len(v),"n":len(v)} if (v:=[q[name][key] for q in complete if q[name][key] is not None]) else {"mean":None,"n":0} for key in keys}
    clusters=defaultdict(list)
    for q in complete:clusters[q["cluster"]].append(q["ndcg5_difference"])
    uncertainty=cluster_bootstrap(dict(clusters))
    mean_diff=sum(q["ndcg5_difference"] for q in complete)/len(complete) if complete else None
    verdict="INSUFFICIENT_INDEPENDENT_EVIDENCE" if mean_diff is None else decision(mean_diff,uncertainty["ci95"][0],len(complete),len(clusters),True)
    return {"status":"PROSPECTIVE_VALIDATION_COMPLETED" if verdict!="INSUFFICIENT_INDEPENDENT_EVIDENCE" else verdict,
        "decision":verdict,"complete_queries":len(complete),"independent_climate_clusters":len(clusters),
        "primary":{"candidate":aggregate("candidate")["ndcg@5"],"baseline":aggregate("baseline")["ndcg@5"],
            "paired_mean_difference":mean_diff,"cluster_bootstrap":uncertainty},
        "candidate_metrics":aggregate("candidate"),"baseline_metrics":aggregate("baseline"),
        "query_results":complete}
