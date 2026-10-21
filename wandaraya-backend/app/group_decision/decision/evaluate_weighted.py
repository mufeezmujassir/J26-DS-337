"""Evaluation script for Step 10b: Emotion-Intensity Weighted Voting (WANDARAYA Component 3).

Evaluates Majority Voting, Preference-Only, and Emotion-Weighted Voting on:
(a) Demo groups (data/processed/decision_demo_groups.json)
(b) Gold structured preferences from custom dataset if present

Calculates:
- Method flip rate vs preference-only
- Tie rate
- Mean preference coverage
- Mean minimum member satisfaction
- Share of groups where a member with a negative stance toward the chosen option exists
- Sensitivity analysis over alpha in {0, 0.25, 0.5, 1.0, 2.0} and w_max in {1.5, 2.0, 3.0}

Saves outputs to:
- reports/weighted_voting_results.json
- reports/figures/weighted_sensitivity.png
- reports/figures/weighted_comparison.png

CRITICAL METHODOLOGICAL NOTE:
Flip rate is NOT accuracy, since there is no ground truth for the correct group
decision, and satisfaction metrics use the same stance information as the vote.
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
from app.group_decision.decision.weighted import weighted_vote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEMO_GROUPS_PATH = ROOT_DIR / "data" /"group_decision" / "processed" / "decision_demo_groups.json"
RESULTS_JSON_PATH = ROOT_DIR / "reports" / "weighted_voting_results.json"
SENSITIVITY_FIGURE_PATH = ROOT_DIR / "reports" / "figures" / "weighted_sensitivity.png"
COMPARISON_FIGURE_PATH = ROOT_DIR / "reports" / "figures" / "weighted_comparison.png"

CANDIDATE_GOLD_PATHS = [
    ROOT_DIR / "data" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "processed" / "gold_structured_preferences.json",
    ROOT_DIR / "data" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
]

SENSITIVITY_ALPHAS = [0.0, 0.25, 0.5, 1.0, 2.0]
SENSITIVITY_W_MAXS = [1.5, 2.0, 3.0]

METHODOLOGICAL_DISCLAIMER = (
    "Flip rate is NOT accuracy, since there is no ground truth for the correct "
    "group decision, and satisfaction metrics use the same stance information as the vote."
)


def evaluate_dataset(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate majority, preference-only, and weighted methods on a set of groups."""
    total_groups = len(groups)
    if total_groups == 0:
        return {"total_groups": 0}

    # Tracking for Majority
    maj_flips = 0
    maj_ties = 0
    maj_coverages: list[float] = []
    maj_min_sats: list[float] = []
    maj_negative_stance_groups = 0

    # Tracking for Preference-Only
    pref_ties = 0
    pref_coverages: list[float] = []
    pref_min_sats: list[float] = []
    pref_negative_stance_groups = 0

    # Tracking for Weighted Voting (default config)
    wgt_flips = 0
    wgt_ties = 0
    wgt_coverages: list[float] = []
    wgt_min_sats: list[float] = []
    wgt_negative_stance_groups = 0

    group_details: list[dict[str, Any]] = []

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        maj_res = decide(records, method="majority", category=category)
        pref_res = decide(records, method="preference_only", category=category)
        wgt_res = decide(records, method="weighted", category=category)

        # Baseline: Preference-only chosen option
        pref_opt = pref_res.chosen_option

        # Majority metrics
        if maj_res.chosen_option != pref_opt:
            maj_flips += 1
        if maj_res.is_tie:
            maj_ties += 1
        maj_cov = preference_coverage(records, maj_res.chosen_option, category=category)
        maj_min_sat = min_member_satisfaction(records, maj_res.chosen_option, category=category)
        maj_coverages.append(maj_cov)
        maj_min_sats.append(maj_min_sat)
        if maj_min_sat == 0.0:
            maj_negative_stance_groups += 1

        # Preference-only metrics
        if pref_res.is_tie:
            pref_ties += 1
        pref_cov = preference_coverage(records, pref_res.chosen_option, category=category)
        pref_min_sat = min_member_satisfaction(records, pref_res.chosen_option, category=category)
        pref_coverages.append(pref_cov)
        pref_min_sats.append(pref_min_sat)
        if pref_min_sat == 0.0:
            pref_negative_stance_groups += 1

        # Weighted metrics
        if wgt_res.outcome_changed_vs_preference_only:
            wgt_flips += 1
        if wgt_res.is_tie:
            wgt_ties += 1
        wgt_cov = preference_coverage(records, wgt_res.chosen_option, category=category)
        wgt_min_sat = min_member_satisfaction(records, wgt_res.chosen_option, category=category)
        wgt_coverages.append(wgt_cov)
        wgt_min_sats.append(wgt_min_sat)
        if wgt_min_sat == 0.0:
            wgt_negative_stance_groups += 1

        group_details.append({
            "group_id": gid,
            "category": category,
            "majority": {
                "chosen": maj_res.chosen_option,
                "is_tie": maj_res.is_tie,
                "coverage": maj_cov,
                "min_sat": maj_min_sat,
            },
            "preference_only": {
                "chosen": pref_res.chosen_option,
                "is_tie": pref_res.is_tie,
                "coverage": pref_cov,
                "min_sat": pref_min_sat,
            },
            "weighted": {
                "chosen": wgt_res.chosen_option,
                "is_tie": wgt_res.is_tie,
                "outcome_changed": wgt_res.outcome_changed_vs_preference_only,
                "coverage": wgt_cov,
                "min_sat": wgt_min_sat,
                "contributions_count": len(wgt_res.contributions),
            },
        })

    return {
        "total_groups": total_groups,
        "majority": {
            "flip_rate_vs_pref": round(maj_flips / total_groups, 4),
            "tie_rate": round(maj_ties / total_groups, 4),
            "mean_preference_coverage": round(float(np.mean(maj_coverages)), 4),
            "mean_min_member_satisfaction": round(float(np.mean(maj_min_sats)), 4),
            "groups_with_negative_stance": maj_negative_stance_groups,
            "negative_stance_rate": round(maj_negative_stance_groups / total_groups, 4),
        },
        "preference_only": {
            "flip_rate_vs_pref": 0.0,
            "tie_rate": round(pref_ties / total_groups, 4),
            "mean_preference_coverage": round(float(np.mean(pref_coverages)), 4),
            "mean_min_member_satisfaction": round(float(np.mean(pref_min_sats)), 4),
            "groups_with_negative_stance": pref_negative_stance_groups,
            "negative_stance_rate": round(pref_negative_stance_groups / total_groups, 4),
        },
        "weighted": {
            "flip_rate_vs_pref": round(wgt_flips / total_groups, 4),
            "tie_rate": round(wgt_ties / total_groups, 4),
            "mean_preference_coverage": round(float(np.mean(wgt_coverages)), 4),
            "mean_min_member_satisfaction": round(float(np.mean(wgt_min_sats)), 4),
            "groups_with_negative_stance": wgt_negative_stance_groups,
            "negative_stance_rate": round(wgt_negative_stance_groups / total_groups, 4),
        },
        "group_details": group_details,
    }


def run_sensitivity_analysis(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run sensitivity analysis across alpha and w_max grid."""
    total_groups = len(groups)
    if total_groups == 0:
        return []

    sensitivity_results: list[dict[str, Any]] = []

    for w_max in SENSITIVITY_W_MAXS:
        for alpha in SENSITIVITY_ALPHAS:
            flips = 0
            ties = 0
            coverages: list[float] = []
            min_sats: list[float] = []
            negative_stance_groups = 0

            for g in groups:
                category = g.get("category", "Destination")
                records = g.get("records", [])

                pref_res = decide(records, method="preference_only", category=category)
                wgt_res = decide(
                    records,
                    method="weighted",
                    category=category,
                    config={"weighted": {"alpha": alpha, "w_max": w_max, "w_min": 1.0}},
                )

                if wgt_res.chosen_option != pref_res.chosen_option:
                    flips += 1
                if wgt_res.is_tie:
                    ties += 1

                cov = preference_coverage(records, wgt_res.chosen_option, category=category)
                min_sat = min_member_satisfaction(records, wgt_res.chosen_option, category=category)
                coverages.append(cov)
                min_sats.append(min_sat)
                if min_sat == 0.0:
                    negative_stance_groups += 1

            sensitivity_results.append({
                "alpha": alpha,
                "w_max": w_max,
                "flip_rate": round(flips / total_groups, 4),
                "tie_rate": round(ties / total_groups, 4),
                "mean_preference_coverage": round(float(np.mean(coverages)), 4),
                "mean_min_member_satisfaction": round(float(np.mean(min_sats)), 4),
                "negative_stance_rate": round(negative_stance_groups / total_groups, 4),
            })

    return sensitivity_results


def plot_comparison_chart(results: dict[str, Any], output_path: Path) -> None:
    """Save 3-way grouped bar chart comparing Majority, Preference-Only, and Weighted."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = [
        "Tie Rate",
        "Mean Coverage",
        "Mean Min Satisfaction",
        "Negative Stance Share",
        "Flip Rate vs Pref",
    ]

    m = results["majority"]
    p = results["preference_only"]
    w = results["weighted"]

    maj_vals = [
        m["tie_rate"],
        m["mean_preference_coverage"],
        m["mean_min_member_satisfaction"],
        m["negative_stance_rate"],
        m["flip_rate_vs_pref"],
    ]
    pref_vals = [
        p["tie_rate"],
        p["mean_preference_coverage"],
        p["mean_min_member_satisfaction"],
        p["negative_stance_rate"],
        p["flip_rate_vs_pref"],
    ]
    wgt_vals = [
        w["tie_rate"],
        w["mean_preference_coverage"],
        w["mean_min_member_satisfaction"],
        w["negative_stance_rate"],
        w["flip_rate_vs_pref"],
    ]

    x = np.arange(len(metrics))
    width = 0.25

    fig, ax = plt.subplots(figsize=(11, 6))
    rects1 = ax.bar(x - width, maj_vals, width, label="Majority Voting", color="#2b5c8f")
    rects2 = ax.bar(x, pref_vals, width, label="Preference-Only", color="#e67e22")
    rects3 = ax.bar(x + width, wgt_vals, width, label="Emotion-Weighted", color="#27ae60")

    ax.set_title(
        "Decision Engine Performance: Majority vs Preference-Only vs Emotion-Weighted Voting\n(WANDARAYA Step 10b)",
        fontsize=12,
        pad=15,
    )
    ax.set_ylabel("Metric Value / Rate", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1.18)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=10)

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
                fontsize=8,
            )

    autolabel(rects1)
    autolabel(rects2)
    autolabel(rects3)

    fig.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info("Saved comparison chart to %s", output_path)


def plot_sensitivity_chart(sensitivity_data: list[dict[str, Any]], output_path: Path) -> None:
    """Save 2-panel sensitivity chart over alpha and w_max."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    colors = {1.5: "#3498db", 2.0: "#2ecc71", 3.0: "#e74c3c"}
    markers = {1.5: "o", 2.0: "s", 3.0: "^"}

    for w_max in SENSITIVITY_W_MAXS:
        subset = [d for d in sensitivity_data if d["w_max"] == w_max]
        subset = sorted(subset, key=lambda d: d["alpha"])

        alphas = [d["alpha"] for d in subset]
        flips = [d["flip_rate"] for d in subset]
        min_sats = [d["mean_min_member_satisfaction"] for d in subset]

        c = colors.get(w_max, "black")
        m = markers.get(w_max, "o")

        ax1.plot(alphas, flips, marker=m, color=c, linewidth=2, label=f"w_max = {w_max}")
        ax2.plot(alphas, min_sats, marker=m, color=c, linewidth=2, label=f"w_max = {w_max}")

    ax1.set_title("Sensitivity: Flip Rate vs Alpha (vs Preference-Only)", fontsize=11)
    ax1.set_xlabel(r"Alpha ($\alpha$)", fontsize=10)
    ax1.set_ylabel("Flip Rate", fontsize=10)
    ax1.set_ylim(-0.05, 1.05)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=9)

    ax2.set_title("Sensitivity: Mean Min Satisfaction vs Alpha", fontsize=11)
    ax2.set_xlabel(r"Alpha ($\alpha$)", fontsize=10)
    ax2.set_ylabel("Mean Min Satisfaction", fontsize=10)
    ax2.set_ylim(-0.05, 1.05)
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(fontsize=9)

    fig.suptitle(
        "Emotion-Intensity Weighted Voting: Sensitivity Analysis (Alpha x W_max)\n"
        "Note: Flip rate is NOT accuracy; satisfaction uses vote stances.",
        fontsize=12,
        y=1.02,
    )
    fig.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info("Saved sensitivity chart to %s", output_path)


def run_evaluation() -> None:
    """Execute complete Step 10b evaluation pipeline."""
    logger.info("Starting Emotion-Intensity Weighted Voting Evaluation (Step 10b)...")

    if not DEMO_GROUPS_PATH.exists():
        logger.error("Demo groups file not found at %s", DEMO_GROUPS_PATH)
        sys.exit(1)

    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        demo_groups = json.load(f)

    logger.info("Loaded %d demo groups from %s", len(demo_groups), DEMO_GROUPS_PATH)
    demo_results = evaluate_dataset(demo_groups)
    sensitivity_results = run_sensitivity_analysis(demo_groups)

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
        "metadata": {
            "evaluation_step": "Step 10b (Emotion-intensity weighted voting)",
            "methodological_disclaimer": METHODOLOGICAL_DISCLAIMER,
        },
        "demo_dataset": {
            "source_file": str(DEMO_GROUPS_PATH),
            "results": demo_results,
            "sensitivity_analysis": sensitivity_results,
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

    # Save visualization figures
    plot_comparison_chart(demo_results, COMPARISON_FIGURE_PATH)
    plot_sensitivity_chart(sensitivity_results, SENSITIVITY_FIGURE_PATH)

    # Print summary console table
    print("\n" + "=" * 80)
    print("STEP 10b: EMOTION-INTENSITY WEIGHTED VOTING EVALUATION REPORT")
    print("=" * 80)
    print(f"Total Groups Evaluated:       {demo_results['total_groups']}")
    print("-" * 80)
    header_fmt = "{:<28} | {:<14} | {:<16} | {:<14}"
    row_fmt    = "{:<28} | {:<14} | {:<16} | {:<14}"
    print(header_fmt.format("Metric", "Majority", "Preference-Only", "Weighted"))
    print("-" * 80)

    m = demo_results["majority"]
    p = demo_results["preference_only"]
    w = demo_results["weighted"]

    print(row_fmt.format(
        "Flip Rate (vs Pref-Only)",
        f"{m['flip_rate_vs_pref'] * 100:.1f}%",
        f"{p['flip_rate_vs_pref'] * 100:.1f}%",
        f"{w['flip_rate_vs_pref'] * 100:.1f}%",
    ))
    print(row_fmt.format(
        "Tie Rate",
        f"{m['tie_rate'] * 100:.1f}%",
        f"{p['tie_rate'] * 100:.1f}%",
        f"{w['tie_rate'] * 100:.1f}%",
    ))
    print(row_fmt.format(
        "Mean Preference Coverage",
        f"{m['mean_preference_coverage']:.4f}",
        f"{p['mean_preference_coverage']:.4f}",
        f"{w['mean_preference_coverage']:.4f}",
    ))
    print(row_fmt.format(
        "Mean Min Satisfaction",
        f"{m['mean_min_member_satisfaction']:.4f}",
        f"{p['mean_min_member_satisfaction']:.4f}",
        f"{w['mean_min_member_satisfaction']:.4f}",
    ))
    print(row_fmt.format(
        "Negative Stance Share",
        f"{m['negative_stance_rate'] * 100:.1f}%",
        f"{p['negative_stance_rate'] * 100:.1f}%",
        f"{w['negative_stance_rate'] * 100:.1f}%",
    ))
    print("=" * 80)
    print("\nMETHODOLOGICAL NOTE:")
    print(f"  * {METHODOLOGICAL_DISCLAIMER}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_evaluation()
