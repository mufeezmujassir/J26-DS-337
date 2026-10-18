"""Validate blinded multi-query labels and calculate judged-pool metrics."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.recommendation.evaluation.human_relevance import disagreement_report, ranking_metrics, validate_annotations


ROOT = Path("data/reports")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-1", default=str(ROOT / "stage12_2f_reviewer_1_template.csv"))
    parser.add_argument("--reviewer-2", default=str(ROOT / "stage12_2f_reviewer_2_template.csv"))
    parser.add_argument("--candidate-universe", default=str(ROOT / "stage12_2f_candidate_universe.json"))
    args = parser.parse_args()
    rows = []
    for path in (Path(args.reviewer_1), Path(args.reviewer_2)):
        rows.extend(csv.DictReader(path.open(encoding="utf-8", newline="")))
    checked = validate_annotations(rows)
    identities = sorted({str(row.get("reviewer_id", "")) for row in rows})
    identity_valid = identities == ["R1", "R2"]
    disagreements = disagreement_report(checked["valid"])
    complete = identity_valid and not checked["missing"] and not checked["duplicates"] and not checked["invalid"] and not disagreements
    integrity = {"status": "LABELS_READY_FOR_MULTI_QUERY_METRICS" if complete else "AWAITING_INDEPENDENT_HUMAN_LABELS", "reviewer_identities": identities, "reviewer_identity_valid": identity_valid, "valid_annotations": len(checked["valid"]), "missing_labels": checked["missing"], "duplicate_labels": checked["duplicates"], "invalid_labels": checked["invalid"], "disagreements": disagreements, "annotation_batches": sorted({str(row.get("annotation_batch_id", "")) for row in rows}), "automatic_adjudication_performed": False}
    (ROOT / "stage12_2f_annotation_integrity.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    if not complete:
        withheld = {"status": "METRICS_WITHHELD_PENDING_COMPLETE_INDEPENDENT_LABELS", "reason": "Both blinded templates need complete, valid, independently supplied labels with disagreements adjudicated.", "postgresql_writes": False, "qdrant_writes": False}
        for filename in ("stage12_2f_per_query_metrics.json", "stage12_2f_macro_metrics.json", "stage12_2f_ranking_error_analysis.json", "stage12_2f_policy_decision.json"):
            (ROOT / filename).write_text(json.dumps(withheld, indent=2) + "\n", encoding="utf-8")
        (ROOT / "stage12_2f_final_summary.json").write_text(json.dumps({"status": "AWAITING_INDEPENDENT_HUMAN_LABELS", "metrics_status": withheld["status"], "production_ranking_policy_changed": False, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(withheld, indent=2)); return
    universe = json.loads(Path(args.candidate_universe).read_text(encoding="utf-8"))["records"]
    labels = {(row["query_id"], str(row["attraction_id"])): row["relevance_0_to_3"] for row in checked["valid"] if row["reviewer_id"] == "R1"}
    per_query = {}
    for query_id in sorted({row["query_id"] for row in universe}):
        records = [row for row in universe if row["query_id"] == query_id]
        query_labels = {str(row["attraction_id"]): labels[(query_id, str(row["attraction_id"]))] for row in records}
        per_query[query_id] = {policy: {**ranking_metrics([str(row["attraction_id"]) for row in sorted(records, key=lambda item: item[field])], query_labels, 5), **ranking_metrics([str(row["attraction_id"]) for row in sorted(records, key=lambda item: item[field])], query_labels, 10)} for policy, field in (("semantic_only", "semantic_rank"), ("content_baseline_v1", "baseline_rank"), ("content_evidence_review_experiment_v1", "experimental_rank"))}
    macro = {policy: {metric: sum(values[policy][metric] for values in per_query.values() if values[policy][metric] is not None) / len([values for values in per_query.values() if values[policy][metric] is not None]) for metric in ("precision_at_5", "judged_pool_recall_at_5", "ndcg_at_5")} for policy in next(iter(per_query.values())).keys()}
    error_analysis = {"status": "REVIEW_REQUIRED", "method": "Use human scores plus eligibility flags in candidate-universe report; no automatic attraction reclassification performed."}
    decision = {"recommendation": "continue_experimental_evaluation", "reason": "Metrics are judged-pool results on bounded candidate sets; a controlled rollout requires a separate review of macro results, error analysis, and selection bias."}
    for filename, body in {"stage12_2f_per_query_metrics.json": {"status": "MULTI_QUERY_EVALUATION_COMPLETED", "per_query": per_query, "recall_scope": "judged-pool only"}, "stage12_2f_macro_metrics.json": {"status": "MULTI_QUERY_EVALUATION_COMPLETED", "macro_averages": macro, "bootstrap_confidence_intervals": "not computed automatically; require review of query independence and sample size"}, "stage12_2f_ranking_error_analysis.json": error_analysis, "stage12_2f_policy_decision.json": decision, "stage12_2f_final_summary.json": {"status": "MULTI_QUERY_EVALUATION_COMPLETED", "production_ranking_policy_changed": False, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0}}.items():
        (ROOT / filename).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "MULTI_QUERY_EVALUATION_COMPLETED", "queries": len(per_query)}, indent=2))


if __name__ == "__main__":
    main()
