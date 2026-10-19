"""Evaluation script for  Rule-based Conflict Detector.

Evaluates the rule-based conflict detector against:
(a) Hand-written test cases (data/processed/conflict_test_cases.json)
(b) Gold structured preferences from custom dataset if present

Calculates per-conflict-type precision, recall, F1, confusion matrix over
{Destination, Budget, Schedule, Activity, None}, logs false positives/negatives,
and saves results and confusion matrix figure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import matplotlib.pyplot as plt
import numpy as np

from app.group_decision.conflict.rules import detect_conflicts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CLASSES = ["Destination", "Budget", "Schedule", "Activity", "None"]

TEST_CASES_PATH = ROOT_DIR / "data" / "group_decision" / "processed" / "conflict_test_cases.json"
RESULTS_JSON_PATH = ROOT_DIR / "data" / "group_decision" / "reports" / "conflict_rules_results.json"
FIGURE_PNG_PATH = ROOT_DIR / "data" / "group_decision" / "reports" / "figures" / "conflict_confusion_matrix.png"

CANDIDATE_GOLD_PATHS = [
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_structured_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
]


def load_test_cases(file_path: Path) -> list[dict[str, Any]]:
    """Load json list of test cases."""
    if not file_path.exists():
        raise FileNotFoundError(f"Test cases file not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    return cases


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Run conflict detector across cases and calculate metrics and errors."""
    y_true: list[str] = []
    y_pred: list[str] = []
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []

    for case in cases:
        gt = case.get("ground_truth_type") or ("None" if not case.get("expected_conflict") else case.get("category_focus"))
        if gt not in CLASSES:
            gt = "None"
        y_true.append(gt)

        records = case.get("records", [])
        detected = detect_conflicts(records)

        if not detected:
            pred = "None"
            rule_fired = None
        else:
            # Check if any detected conflict matches ground truth
            matching = next((c for c in detected if c["type"] == gt), None)
            if matching:
                pred = matching["type"]
                rule_fired = matching["rule_id"]
            else:
                pred = detected[0]["type"]
                rule_fired = detected[0]["rule_id"]

        y_pred.append(pred)

        # Track false positives and negatives
        if pred != gt:
            if gt == "None":
                false_positives.append({
                    "case_id": case.get("case_id"),
                    "name": case.get("name"),
                    "ground_truth": gt,
                    "predicted": pred,
                    "rule_fired": rule_fired,
                    "detected_conflicts": detected,
                })
            elif pred == "None":
                false_negatives.append({
                    "case_id": case.get("case_id"),
                    "name": case.get("name"),
                    "ground_truth": gt,
                    "predicted": pred,
                    "rule_fired": None,
                })
            else:
                false_positives.append({
                    "case_id": case.get("case_id"),
                    "name": case.get("name"),
                    "ground_truth": gt,
                    "predicted": pred,
                    "rule_fired": rule_fired,
                    "detected_conflicts": detected,
                })
                false_negatives.append({
                    "case_id": case.get("case_id"),
                    "name": case.get("name"),
                    "ground_truth": gt,
                    "predicted": pred,
                    "rule_fired": None,
                })

    # Confusion matrix
    label_to_idx = {label: i for i, label in enumerate(CLASSES)}
    cm = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    for yt, yp in zip(y_true, y_pred):
        cm[label_to_idx[yt]][label_to_idx[yp]] += 1

    # Per-class metrics
    per_class_metrics: dict[str, dict[str, float | int]] = {}
    for c in CLASSES:
        idx = label_to_idx[c]
        tp = int(cm[idx, idx])
        fp = int(cm[:, idx].sum() - tp)
        fn = int(cm[idx, :].sum() - tp)
        support = int(cm[idx, :].sum())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        per_class_metrics[c] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": support,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    # Macro averages over conflict types (excluding 'None')
    conflict_types = ["Destination", "Budget", "Schedule", "Activity"]
    macro_precision = float(np.mean([per_class_metrics[ct]["precision"] for ct in conflict_types]))
    macro_recall = float(np.mean([per_class_metrics[ct]["recall"] for ct in conflict_types]))
    macro_f1 = float(np.mean([per_class_metrics[ct]["f1"] for ct in conflict_types]))

    return {
        "total_cases": len(cases),
        "confusion_matrix": {
            "classes": CLASSES,
            "matrix": cm.tolist(),
        },
        "per_conflict_type": per_class_metrics,
        "macro_metrics_conflict_types": {
            "precision": round(macro_precision, 4),
            "recall": round(macro_recall, 4),
            "f1": round(macro_f1, 4),
        },
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def plot_confusion_matrix(cm_data: list[list[int]], classes: list[str], output_path: Path) -> None:
    """Render and save publication-quality confusion matrix image."""
    cm = np.array(cm_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.figure.colorbar(im, ax=ax)

    ax.set(
        xticks=np.arange(cm.shape[1]),
        yticks=np.arange(cm.shape[0]),
        xticklabels=classes,
        yticklabels=classes,
        title="Conflict Detector Confusion Matrix\n(Step 9: Rule-based)",
        ylabel="True Label",
        xlabel="Predicted Label",
    )

    plt.setp(ax.get_xticklabels(), rotation=35, ha="right", rotation_mode="anchor")

    thresh = cm.max() / 2.0 if cm.max() > 0 else 1.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            val = cm[i, j]
            color = "white" if val > thresh else "black"
            ax.text(j, i, f"{val:d}", ha="center", va="center", color=color, fontsize=12, fontweight="bold")

    fig.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info("Saved confusion matrix figure to %s", output_path)


def run_evaluation() -> None:
    """Execute complete evaluation workflow."""
    logger.info("Starting Rule-Based Conflict Detector Evaluation...")

    # 1. Evaluate synthetic hand-written test cases
    cases = load_test_cases(TEST_CASES_PATH)
    logger.info("Loaded %d test cases from %s", len(cases), TEST_CASES_PATH)
    results = evaluate_cases(cases)

    # 2. Check for optional gold custom dataset
    gold_results: dict[str, Any] | None = None
    gold_path_used: str | None = None
    for p in CANDIDATE_GOLD_PATHS:
        if p.exists():
            logger.info("Found custom gold dataset at %s. Evaluating...", p)
            try:
                gold_cases = load_test_cases(p)
                gold_results = evaluate_cases(gold_cases)
                gold_path_used = str(p)
                break
            except Exception as e:
                logger.warning("Failed evaluating gold dataset at %s: %s", p, e)

    # Combine output report
    output_report = {
        "primary_dataset": {
            "source_file": str(TEST_CASES_PATH),
            "results": results,
        },
        "custom_gold_dataset": {
            "evaluated": gold_results is not None,
            "source_file": gold_path_used,
            "results": gold_results,
        },
    }

    # Save JSON report
    RESULTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_report, f, indent=2)
    logger.info("Saved evaluation results to %s", RESULTS_JSON_PATH)

    # Plot and save confusion matrix figure
    plot_confusion_matrix(
        results["confusion_matrix"]["matrix"],
        CLASSES,
        FIGURE_PNG_PATH,
    )

    # Print summary to console
    print("\n" + "=" * 70)
    print("STEP 9: RULE-BASED CONFLICT DETECTOR EVALUATION REPORT")
    print("=" * 70)
    print(f"Total Cases Evaluated: {results['total_cases']}")
    print("-" * 70)
    print(f"{'Class':<15} {'Support':<10} {'Precision':<12} {'Recall':<10} {'F1-Score':<10}")
    print("-" * 70)
    for c in CLASSES:
        m = results["per_conflict_type"][c]
        print(f"{c:<15} {m['support']:<10} {m['precision']:<12.4f} {m['recall']:<10.4f} {m['f1']:<10.4f}")
    print("-" * 70)
    macro = results["macro_metrics_conflict_types"]
    print(f"{'Macro (Rules)':<15} {'-':<10} {macro['precision']:<12.4f} {macro['recall']:<10.4f} {macro['f1']:<10.4f}")
    print("=" * 70)
    print(f"False Positives: {len(results['false_positives'])}")
    print(f"False Negatives: {len(results['false_negatives'])}")
    if results['false_positives']:
        print("\nFalse Positives detail:")
        for fp in results['false_positives']:
            print(f"  - [{fp['case_id']}] {fp['name']}: predicted {fp['predicted']} (rule: {fp['rule_fired']})")
    if results['false_negatives']:
        print("\nFalse Negatives detail:")
        for fn in results['false_negatives']:
            print(f"  - [{fn['case_id']}] {fn['name']}: ground truth {fn['ground_truth']} not detected")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_evaluation()
