"""Validate two reviewer files and calculate judged-pool metrics after labeling."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.recommendation.evaluation.human_relevance import disagreement_report, ranking_metrics, validate_annotations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-1", required=True)
    parser.add_argument("--reviewer-2", required=True)
    args = parser.parse_args()
    rows = []
    for path in (Path(args.reviewer_1), Path(args.reviewer_2)):
        rows.extend(csv.DictReader(path.open(encoding="utf-8", newline="")))
    checked = validate_annotations(rows)
    disagreements = disagreement_report(checked["valid"])
    complete = not checked["missing"] and not checked["duplicates"] and not checked["invalid"]
    unresolved = [row for row in disagreements if row["requires_adjudication"]]
    status = "AWAITING_HUMAN_RELEVANCE_LABELS" if not complete else ("LABELS_VALIDATED_AWAITING_ADJUDICATION" if unresolved else "HUMAN_RANKING_EVALUATION_COMPLETED")
    report = {"status": status, "valid_annotations": len(checked["valid"]), "missing_labels": checked["missing"], "duplicate_labels": checked["duplicates"], "invalid_labels": checked["invalid"], "disagreements": disagreements, "unresolved_disagreement_count": len(unresolved), "automatic_adjudication_performed": False}
    root = Path("data/reports")
    (root / "stage12_2e_label_quality.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if status != "HUMAN_RANKING_EVALUATION_COMPLETED":
        metrics = {"status": "METRICS_WITHHELD_PENDING_COMPLETE_CONSENSUS", "reason": "Independent labels must be complete and disagreements resolved.", "metric_definitions": {"binary_relevance": "score >= 2", "recall": "judged-pool recall only unless the full relevance universe is judged."}}
    else:
        by_query: dict[str, list[dict]] = {}
        for row in checked["valid"]:
            by_query.setdefault(str(row["query_id"]), []).append(row)
        per_query = {}
        for query_id, query_rows in by_query.items():
            # Equal independent scores are the adjudicated consensus here.
            labels = {str(row["attraction_id"]): row["relevance_0_to_3"] for row in query_rows if str(row["reviewer_id"]) == "R1"}
            representative = [row for row in query_rows if str(row["reviewer_id"]) == "R1"]
            policies = {}
            for field, name in (("baseline_rank", "content_baseline_v1"), ("experimental_rank", "content_evidence_review_experiment_v1")):
                ranked_ids = [str(row["attraction_id"]) for row in sorted(representative, key=lambda item: int(item[field]))]
                policies[name] = {**ranking_metrics(ranked_ids, labels, 5), **ranking_metrics(ranked_ids, labels, 10)}
            per_query[query_id] = policies
        metrics = {"status": "JUDGED_POOL_METRICS_COMPLETED", "binary_relevance": "human score >= 2", "recall_scope": "judged-pool only; this is not global attraction recall", "per_query": per_query, "unavailable_policy_comparisons": ["semantic_only: equivalent saved ranking unavailable", "time_aware: equivalent candidate universe and visit-time ranking unavailable"], "statistical_significance_claimed": False, "limitation": "One labeled query is insufficient for statistical inference or a production policy decision."}
    (root / "stage12_2e_ranking_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (root / "stage12_2e_final_summary.json").write_text(json.dumps({"status": status, "valid_annotations": len(checked["valid"]), "unresolved_disagreements": len(unresolved), "metrics_status": metrics["status"], "production_ranking_policy_changed": False, "postgresql_writes": False, "qdrant_writes": False, "groq_requests": 0}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
