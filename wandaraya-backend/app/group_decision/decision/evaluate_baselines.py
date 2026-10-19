"""Evaluation script for Step 10a: Decision Engine Baselines (WANDARAYA Component 3).

Evaluates Majority Voting and Preference-Only aggregation on:
(a) Demo groups (data/processed/decision_demo_groups.json)
(b) Gold structured preferences from custom dataset if present

Calculates:
- Method agreement rate
- Tie rates
- Majority-present rates
- Mean preference coverage
- Mean minimum member satisfaction
- Count of groups with negative stance towards chosen option

Saves outputs to:
- reports/decision_baselines_results.json
- reports/figures/decision_baselines_comparison.png
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.decision.baselines import decide
from app.group_decision.decision.metrics import min_member_satisfaction, preference_coverage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEMO_GROUPS_PATH = ROOT_DIR / "data" / "group_decision" / "processed" / "decision_demo_groups.json"
RESULTS_JSON_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "decision_baselines_results.json"
FIGURE_PNG_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "figures" / "decision_baselines_comparison.png"

CANDIDATE_GOLD_PATHS = [
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_structured_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
]


def evaluate_dataset(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate baseline methods on a set of groups."""
    total_groups = len(groups)
    if total_groups == 0:
        return {"total_groups": 0}

    agreed_count = 0

    maj_ties = 0
    maj_has_majority = 0
    maj_coverages: list[float] = []
    maj_min_sats: list[float] = []
    maj_negative_stance_groups = 0

    pref_ties = 0
    pref_has_majority = 0
    pref_coverages: list[float] = []
    pref_min_sats: list[float] = []
    pref_negative_stance_groups = 0

    group_details: list[dict[str, Any]] = []

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        maj_res = decide(records, method="majority", category=category)
        pref_res = decide(records, method="preference_only", category=category)

        # Agreement
        agreed = (maj_res.chosen_option == pref_res.chosen_option)
        if agreed:
            agreed_count += 1

        # Majority metrics
        if maj_res.is_tie:
            maj_ties += 1
        if maj_res.has_majority:
            maj_has_majority += 1
        maj_cov = preference_coverage(records, maj_res.chosen_option, category=category)
        maj_min_sat = min_member_satisfaction(records, maj_res.chosen_option, category=category)
        maj_coverages.append(maj_cov)
        maj_min_sats.append(maj_min_sat)
        if maj_min_sat == 0.0:
            maj_negative_stance_groups += 1

        # Preference-only metrics
        if pref_res.is_tie:
            pref_ties += 1
        if pref_res.has_majority:
            pref_has_majority += 1
        pref_cov = preference_coverage(records, pref_res.chosen_option, category=category)
        pref_min_sat = min_member_satisfaction(records, pref_res.chosen_option, category=category)
        pref_coverages.append(pref_cov)
        pref_min_sats.append(pref_min_sat)
        if pref_min_sat == 0.0:
            pref_negative_stance_groups += 1

        group_details.append({
            "group_id": gid,
            "category": category,
            "agreed": agreed,
            "majority": {
                "chosen": maj_res.chosen_option,
                "is_tie": maj_res.is_tie,
                "has_majority": maj_res.has_majority,
                "coverage": maj_cov,
                "min_satisfaction": maj_min_sat,
            },
            "preference_only": {
                "chosen": pref_res.chosen_option,
                "is_tie": pref_res.is_tie,
                "has_majority": pref_res.has_majority,
                "coverage": pref_cov,
                "min_satisfaction": pref_min_sat,
            },
        })

    return {
        "total_groups": total_groups,
        "agreement_rate": round(agreed_count / total_groups, 4),
        "majority": {
            "tie_rate": round(maj_ties / total_groups, 4),
            "majority_present_rate": round(maj_has_majority / total_groups, 4),
            "mean_preference_coverage": round(float(np.mean(maj_coverages)), 4),
            "mean_min_member_satisfaction": round(float(np.mean(maj_min_sats)), 4),
            "groups_with_negative_stance": maj_negative_stance_groups,
            "negative_stance_rate": round(maj_negative_stance_groups / total_groups, 4),
        },
        "preference_only": {
            "tie_rate": round(pref_ties / total_groups, 4),
            "majority_present_rate": round(pref_has_majority / total_groups, 4),
            "mean_preference_coverage": round(float(np.mean(pref_coverages)), 4),
            "mean_min_member_satisfaction": round(float(np.mean(pref_min_sats)), 4),
            "groups_with_negative_stance": pref_negative_stance_groups,
            "negative_stance_rate": round(pref_negative_stance_groups / total_groups, 4),
        },
        "group_details": group_details,
    }


def plot_comparison_chart(results: dict[str, Any], output_path: Path) -> None:
    """Plot comparative grouped bar chart for Majority vs Preference-Only baselines."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = [
        "Tie Rate",
        "Majority-Present",
        "Mean Coverage",
        "Mean Min Sat.",
        "Negative Stance Rate",
    ]

    maj_data = results["majority"]
    pref_data = results["preference_only"]

    maj_vals = [
        maj_data["tie_rate"],
        maj_data["majority_present_rate"],
        maj_data["mean_preference_coverage"],
        maj_data["mean_min_member_satisfaction"],
        maj_data["negative_stance_rate"],
    ]

    pref_vals = [
        pref_data["tie_rate"],
        pref_data["majority_present_rate"],
        pref_data["mean_preference_coverage"],
        pref_data["mean_min_member_satisfaction"],
        pref_data["negative_stance_rate"],
    ]

    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 5))
    rects1 = ax.bar(x - width / 2, maj_vals, width, label="Majority Voting", color="#2b5c8f")
    rects2 = ax.bar(x + width / 2, pref_vals, width, label="Preference-Only", color="#e27c38")

    ax.set_ylabel("Score / Rate [0.0 - 1.0]", fontsize=11)
    ax.set_title(
        f"Decision Engine Baseline Comparison (Step 10a)\nAgreement Rate: {results['agreement_rate'] * 100:.1f}%",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=10)

    # Annotate bar values
    def autolabel(rects: Any) -> None:
        for rect in rects:
            height = rect.get_height()
            ax.annotate(
                f"{height:.2f}",
                xy=(rect.get_x() + rect.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    autolabel(rects1)
    autolabel(rects2)

    fig.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info("Saved comparison chart to %s", output_path)


def run_evaluation() -> None:
    """Execute complete baselines evaluation."""
    logger.info("Starting Decision Engine Baselines Evaluation...")

    if not DEMO_GROUPS_PATH.exists():
        logger.error("Demo groups file not found at %s", DEMO_GROUPS_PATH)
        sys.exit(1)

    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        demo_groups = json.load(f)

    logger.info("Loaded %d demo groups from %s", len(demo_groups), DEMO_GROUPS_PATH)
    demo_results = evaluate_dataset(demo_groups)

    # Check for custom gold dataset
    gold_results: dict[str, Any] | None = None
    gold_path_used: str | None = None
    for p in CANDIDATE_GOLD_PATHS:
        if p.exists():
            logger.info("Found custom gold dataset at %s. Evaluating...", p)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    gold_groups = json.load(f)
                if isinstance(gold_groups, list):
                    gold_results = evaluate_dataset(gold_groups)
                    gold_path_used = str(p)
                    break
            except Exception as e:
                logger.warning("Failed evaluating gold dataset at %s: %s", p, e)

    output_report = {
        "demo_dataset": {
            "source_file": str(DEMO_GROUPS_PATH),
            "results": demo_results,
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

    # Save bar chart
    plot_comparison_chart(demo_results, FIGURE_PNG_PATH)

    # Print summary
    print("\n" + "=" * 70)
    print("STEP 10a: DECISION ENGINE BASELINES EVALUATION REPORT")
    print("=" * 70)
    print(f"Total Groups Evaluated:       {demo_results['total_groups']}")
    print(f"Method Agreement Rate:        {demo_results['agreement_rate'] * 100:.1f}%")
    print("-" * 70)
    print(f"{'Metric':<32} {'Majority Voting':<18} {'Preference-Only':<18}")
    print("-" * 70)
    m = demo_results["majority"]
    p = demo_results["preference_only"]
    print(f"{'Tie Rate':<32} {m['tie_rate'] * 100:<17.1f}% {p['tie_rate'] * 100:<17.1f}%")
    print(f"{'Majority-Present Rate':<32} {m['majority_present_rate'] * 100:<17.1f}% {p['majority_present_rate'] * 100:<17.1f}%")
    print(f"{'Mean Preference Coverage':<32} {m['mean_preference_coverage']:<18.4f} {p['mean_preference_coverage']:<18.4f}")
    print(f"{'Mean Min Member Satisfaction':<32} {m['mean_min_member_satisfaction']:<18.4f} {p['mean_min_member_satisfaction']:<18.4f}")
    print(f"{'Groups with Negative Stance':<32} {m['groups_with_negative_stance']:<18} {p['groups_with_negative_stance']:<18}")
    print(f"{'Negative Stance Rate':<32} {m['negative_stance_rate'] * 100:<17.1f}% {p['negative_stance_rate'] * 100:<17.1f}%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_evaluation()
