"""Evaluation script for Step 10d: Minority Preference Protection and Compromise Generator.

Compares four methods:
1. Preference-Only (single winner)
2. Weighted Voting (single winner)
3. Weighted + Minority Protection (compromise plan skeleton)
4. Naive 'Union-All' Baseline (includes all liked options)

Reports:
- Mean preference coverage
- Minimum member satisfaction
- Satisfaction gap (max - min)
- Mean satisfaction of members covered by the primary winner (majority protection check)
- Share of groups where protection triggered
- Mean plan size
- Soft conflicts resolved
- Unresolved rejections count
- Sensitivity analysis over slots {1, 2, 3, 4}, min_strength {1.0, 1.2, 1.5}, solver {greedy, exact}

Saves outputs to:
- reports/minority_protection_results.json
- reports/figures/minority_comparison.png
- reports/figures/minority_sensitivity.png

METHODOLOGICAL NOTE:
Coverage gains are partly by construction (the mechanism directly optimizes coverage),
satisfaction uses the same stance information as the decision, and the real fairness
test is the user study with blind ratings. Cost side metrics (plan size and majority
satisfaction) must be evaluated alongside coverage improvements.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.baselines import decide
from app.group_decision.decision.metrics import (
    _deduplicate_records,
    member_satisfaction,
    member_satisfaction_plan,
    min_member_satisfaction,
    min_member_satisfaction_plan,
    preference_coverage,
    preference_coverage_plan,
    satisfaction_gap,
)
from app.group_decision.decision.minority import protect_minority

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEMO_GROUPS_PATH = ROOT_DIR / "data" /"group_decision" / "processed" / "decision_demo_groups.json"
RESULTS_JSON_PATH = ROOT_DIR / "reports" / "minority_protection_results.json"
COMPARISON_FIG_PATH = ROOT_DIR / "reports" / "figures" / "minority_comparison.png"
SENSITIVITY_FIG_PATH = ROOT_DIR / "reports" / "figures" / "minority_sensitivity.png"

CANDIDATE_GOLD_PATHS = [
    ROOT_DIR / "data" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "processed" / "gold_structured_preferences.json",
    ROOT_DIR / "data" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
]

SENSITIVITY_SLOTS = [1, 2, 3, 4]
SENSITIVITY_MIN_STRENGTHS = [1.0, 1.2, 1.5]
SENSITIVITY_SOLVERS = ["greedy", "exact"]

METHODOLOGICAL_NOTE = (
    "Coverage gains are partly by construction (the mechanism directly optimizes coverage), "
    "satisfaction uses the same stance information as the decision, and the real fairness "
    "test is the user study with blind ratings. Cost side: plan size and majority satisfaction."
)


def run_union_all(records: list[Any], category: str) -> list[str]:
    """Naive baseline: include every distinct liked option in the plan."""
    member_stances = _deduplicate_records(records, category=category)
    liked_options: set[str] = set()
    for m, stances in member_stances.items():
        for opt, st in stances.items():
            if st == "positive":
                liked_options.add(opt)
    return sorted(list(liked_options))


def evaluate_dataset(
    groups: list[dict[str, Any]],
    conflicts_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate preference_only, weighted, weighted_minority, and union_all across groups."""
    total_groups = len(groups)
    if total_groups == 0:
        return {"total_groups": 0}

    # Tracking metrics per method
    metrics_tracker: dict[str, dict[str, list[float]]] = {
        "preference_only": {"cov": [], "min_sat": [], "gap": [], "maj_sat": [], "plan_size": []},
        "weighted": {"cov": [], "min_sat": [], "gap": [], "maj_sat": [], "plan_size": []},
        "weighted_minority": {"cov": [], "min_sat": [], "gap": [], "maj_sat": [], "plan_size": []},
        "union_all": {"cov": [], "min_sat": [], "gap": [], "maj_sat": [], "plan_size": []},
    }

    protection_triggered_count = 0
    total_soft_conflicts_resolved = 0
    total_unresolved_rejections = 0

    group_details: list[dict[str, Any]] = []

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # 1. Preference-only
        pref_res = decide(records, method="preference_only", category=category)
        p_opt = pref_res.chosen_option
        p_items = [p_opt] if p_opt else []
        p_cov = preference_coverage_plan(records, p_items, category=category)
        p_sat_map = member_satisfaction_plan(records, p_items, category=category)
        p_min_sat = min(p_sat_map.values()) if p_sat_map else 0.0
        p_gap = satisfaction_gap(p_sat_map)

        # 2. Weighted
        wgt_res = decide(records, method="weighted", category=category)
        w_opt = wgt_res.chosen_option
        w_items = [w_opt] if w_opt else []
        w_cov = preference_coverage_plan(records, w_items, category=category)
        w_sat_map = member_satisfaction_plan(records, w_items, category=category)
        w_min_sat = min(w_sat_map.values()) if w_sat_map else 0.0
        w_gap = satisfaction_gap(w_sat_map)

        # 3. Weighted + Minority Protection
        min_res = decide(
            records,
            method="weighted_minority",
            category=category,
            config={"conflicts": conflicts_data},
        )
        m_items = [p["item"] for p in min_res.plan] if min_res.plan else ([min_res.chosen_option] if min_res.chosen_option else [])
        m_cov = preference_coverage_plan(records, m_items, category=category)
        m_sat_map = member_satisfaction_plan(records, m_items, category=category)
        m_min_sat = min(m_sat_map.values()) if m_sat_map else 0.0
        m_gap = satisfaction_gap(m_sat_map)

        if min_res.protection_applied:
            protection_triggered_count += 1
        total_soft_conflicts_resolved += len(min_res.resolved_conflicts or [])
        total_unresolved_rejections += len(min_res.unresolved_rejection or [])

        # 4. Naive Union-All Baseline
        u_items = run_union_all(records, category=category)
        u_cov = preference_coverage_plan(records, u_items, category=category)
        u_sat_map = member_satisfaction_plan(records, u_items, category=category)
        u_min_sat = min(u_sat_map.values()) if u_sat_map else 0.0
        u_gap = satisfaction_gap(u_sat_map)

        # Majority member satisfaction check (members who liked primary option)
        # Verify the majority's satisfaction is not hurt by compromise items
        member_stances = _deduplicate_records(records, category=category)
        primary_opt_canon = normalize_name(min_res.primary_option, category=category) if min_res.primary_option else None
        majority_members = [
            m for m, st in member_stances.items() if st.get(primary_opt_canon) == "positive"
        ] if primary_opt_canon else []

        def get_maj_sat(sat_map: dict[str, float]) -> float:
            if not majority_members:
                return float(np.mean(list(sat_map.values()))) if sat_map else 0.5
            return float(np.mean([sat_map.get(m, 0.5) for m in majority_members]))

        p_maj_sat = get_maj_sat(p_sat_map)
        w_maj_sat = get_maj_sat(w_sat_map)
        m_maj_sat = get_maj_sat(m_sat_map)
        u_maj_sat = get_maj_sat(u_sat_map)

        # Record metrics
        metrics_tracker["preference_only"]["cov"].append(p_cov)
        metrics_tracker["preference_only"]["min_sat"].append(p_min_sat)
        metrics_tracker["preference_only"]["gap"].append(p_gap)
        metrics_tracker["preference_only"]["maj_sat"].append(p_maj_sat)
        metrics_tracker["preference_only"]["plan_size"].append(len(p_items))

        metrics_tracker["weighted"]["cov"].append(w_cov)
        metrics_tracker["weighted"]["min_sat"].append(w_min_sat)
        metrics_tracker["weighted"]["gap"].append(w_gap)
        metrics_tracker["weighted"]["maj_sat"].append(w_maj_sat)
        metrics_tracker["weighted"]["plan_size"].append(len(w_items))

        metrics_tracker["weighted_minority"]["cov"].append(m_cov)
        metrics_tracker["weighted_minority"]["min_sat"].append(m_min_sat)
        metrics_tracker["weighted_minority"]["gap"].append(m_gap)
        metrics_tracker["weighted_minority"]["maj_sat"].append(m_maj_sat)
        metrics_tracker["weighted_minority"]["plan_size"].append(len(m_items))

        metrics_tracker["union_all"]["cov"].append(u_cov)
        metrics_tracker["union_all"]["min_sat"].append(u_min_sat)
        metrics_tracker["union_all"]["gap"].append(u_gap)
        metrics_tracker["union_all"]["maj_sat"].append(u_maj_sat)
        metrics_tracker["union_all"]["plan_size"].append(len(u_items))

        group_details.append({
            "group_id": gid,
            "category": category,
            "preference_only": {"winner": p_opt, "cov": p_cov, "min_sat": p_min_sat},
            "weighted": {"winner": w_opt, "cov": w_cov, "min_sat": w_min_sat},
            "weighted_minority": {
                "primary": min_res.primary_option,
                "plan": [p["item"] for p in min_res.plan],
                "protection_applied": min_res.protection_applied,
                "cov": m_cov,
                "min_sat": m_min_sat,
                "gap": m_gap,
            },
            "union_all": {"plan": u_items, "cov": u_cov, "min_sat": u_min_sat, "gap": u_gap},
        })

    summary: dict[str, Any] = {"total_groups": total_groups}
    for method, vals in metrics_tracker.items():
        summary[method] = {
            "mean_coverage": round(float(np.mean(vals["cov"])), 4),
            "mean_min_satisfaction": round(float(np.mean(vals["min_sat"])), 4),
            "mean_satisfaction_gap": round(float(np.mean(vals["gap"])), 4),
            "mean_majority_satisfaction": round(float(np.mean(vals["maj_sat"])), 4),
            "mean_plan_size": round(float(np.mean(vals["plan_size"])), 2),
        }

    summary["weighted_minority"]["protection_triggered_share"] = round(
        protection_triggered_count / total_groups, 4
    )
    summary["weighted_minority"]["soft_conflicts_resolved_count"] = total_soft_conflicts_resolved
    summary["weighted_minority"]["unresolved_rejections_count"] = total_unresolved_rejections
    summary["group_details"] = group_details

    return summary


def run_sensitivity_analysis(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run sensitivity analysis over slots {1, 2, 3, 4}, min_strength {1.0, 1.2, 1.5}, solver {greedy, exact}."""
    total_groups = len(groups)
    if total_groups == 0:
        return []

    sensitivity_rows: list[dict[str, Any]] = []

    for slots_num in SENSITIVITY_SLOTS:
        slots_list = [f"slot_{i+1}" for i in range(slots_num)]
        for min_str in SENSITIVITY_MIN_STRENGTHS:
            for solver in SENSITIVITY_SOLVERS:
                covs: list[float] = []
                min_sats: list[float] = []
                gaps: list[float] = []
                plan_sizes: list[float] = []
                protection_count = 0

                for g in groups:
                    category = g.get("category", "Destination")
                    records = g.get("records", [])

                    custom_cfg = {
                        "minority": {
                            "slots": slots_list,
                            "min_strength": min_str,
                            "solver": solver,
                            "enabled": True,
                        }
                    }

                    res = decide(
                        records,
                        method="weighted_minority",
                        category=category,
                        config=custom_cfg,
                    )

                    plan_items = [p["item"] for p in res.plan] if res.plan else []
                    cov = preference_coverage_plan(records, plan_items, category=category)
                    min_sat = min_member_satisfaction_plan(records, plan_items, category=category)
                    gap = satisfaction_gap(records, plan_items, category=category)

                    covs.append(cov)
                    min_sats.append(min_sat)
                    gaps.append(gap)
                    plan_sizes.append(len(plan_items))
                    if res.protection_applied:
                        protection_count += 1

                sensitivity_rows.append({
                    "slots": slots_num,
                    "min_strength": min_str,
                    "solver": solver,
                    "mean_coverage": round(float(np.mean(covs)), 4),
                    "mean_min_satisfaction": round(float(np.mean(min_sats)), 4),
                    "mean_satisfaction_gap": round(float(np.mean(gaps)), 4),
                    "mean_plan_size": round(float(np.mean(plan_sizes)), 2),
                    "protection_triggered_rate": round(protection_count / total_groups, 4),
                })

    return sensitivity_rows


def plot_comparison_chart(results: dict[str, Any], output_path: Path) -> None:
    """Save 4-way bar chart comparing Preference-Only, Weighted, Minority, and Union-All."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = [
        "Mean Coverage",
        "Min Satisfaction",
        "Satisfaction Gap",
        "Majority Sat.",
        "Plan Size (x0.2)",  # scaled down for visualization
    ]

    methods = ["preference_only", "weighted", "weighted_minority", "union_all"]
    labels = ["Preference-Only", "Weighted", "Weighted + Minority", "Naive Union-All"]
    colors = ["#7f8c8d", "#2980b9", "#27ae60", "#e74c3c"]

    data: dict[str, list[float]] = {}
    for m in methods:
        info = results[m]
        data[m] = [
            info["mean_coverage"],
            info["mean_min_satisfaction"],
            info["mean_satisfaction_gap"],
            info["mean_majority_satisfaction"],
            round(info["mean_plan_size"] * 0.2, 3),
        ]

    x = np.arange(len(metrics))
    width = 0.2

    fig, ax = plt.subplots(figsize=(12, 6))

    for idx, (m, lbl, col) in enumerate(zip(methods, labels, colors)):
        rects = ax.bar(x + (idx - 1.5) * width, data[m], width, label=lbl, color=col)
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

    ax.set_title(
        "Compromise Decision Comparison: Baselines vs Minority Protection vs Union-All\n"
        "(WANDARAYA Step 10d: Minority Protection & Compromise Generator)",
        fontsize=12,
        pad=15,
    )
    ax.set_ylabel("Metric Value / Scaled Score", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1.25)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=10)

    fig.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info("Saved comparison chart to %s", output_path)


def plot_sensitivity_chart(sensitivity_data: list[dict[str, Any]], output_path: Path) -> None:
    """Save 3-panel sensitivity plot over slots, min_strength, and solver."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    styles = {
        (1.0, "greedy"): ("#27ae60", "o", "-"),
        (1.0, "exact"): ("#2ecc71", "s", "--"),
        (1.2, "greedy"): ("#2980b9", "o", "-"),
        (1.2, "exact"): ("#3498db", "s", "--"),
        (1.5, "greedy"): ("#8e44ad", "o", "-"),
        (1.5, "exact"): ("#9b59b6", "s", "--"),
    }

    slots_x = SENSITIVITY_SLOTS

    for (min_str, solver), (color, marker, ls) in styles.items():
        subset = [
            d for d in sensitivity_data
            if d["min_strength"] == min_str and d["solver"] == solver
        ]
        subset = sorted(subset, key=lambda d: d["slots"])

        covs = [d["mean_coverage"] for d in subset]
        min_sats = [d["mean_min_satisfaction"] for d in subset]
        plan_sizes = [d["mean_plan_size"] for d in subset]

        lbl = f"str>={min_str}, {solver}"
        ax1.plot(slots_x, covs, color=color, marker=marker, linestyle=ls, label=lbl)
        ax2.plot(slots_x, min_sats, color=color, marker=marker, linestyle=ls, label=lbl)
        ax3.plot(slots_x, plan_sizes, color=color, marker=marker, linestyle=ls, label=lbl)

    ax1.set_title("Coverage vs Plan Slots", fontsize=11)
    ax1.set_xlabel("Slots Count", fontsize=10)
    ax1.set_ylabel("Mean Preference Coverage", fontsize=10)
    ax1.set_ylim(0.4, 1.05)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=8)

    ax2.set_title("Min Satisfaction vs Plan Slots", fontsize=11)
    ax2.set_xlabel("Slots Count", fontsize=10)
    ax2.set_ylabel("Mean Min Member Satisfaction", fontsize=10)
    ax2.set_ylim(0.2, 1.05)
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(fontsize=8)

    ax3.set_title("Mean Plan Size vs Plan Slots", fontsize=11)
    ax3.set_xlabel("Slots Count", fontsize=10)
    ax3.set_ylabel("Mean Plan Size", fontsize=10)
    ax3.grid(True, linestyle="--", alpha=0.5)
    ax3.legend(fontsize=8)

    fig.suptitle(
        "Minority Protection Sensitivity Analysis: Slots x Min-Strength x Solver\n"
        "Note: Coverage gains are partly by construction; real fairness is tested in user studies.",
        fontsize=12,
        y=1.03,
    )
    fig.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info("Saved sensitivity chart to %s", output_path)


def run_evaluation() -> None:
    """Execute complete Step 10d evaluation pipeline."""
    logger.info("Starting Minority Protection & Compromise Generator Evaluation (Step 10d)...")

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
            "evaluation_step": "Step 10d (Minority preference protection and compromise generator)",
            "methodological_disclaimer": METHODOLOGICAL_NOTE,
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

    # Save plots
    plot_comparison_chart(demo_results, COMPARISON_FIG_PATH)
    plot_sensitivity_chart(sensitivity_results, SENSITIVITY_FIG_PATH)

    # Print summary console table
    print("\n" + "=" * 92)
    print("STEP 10d: MINORITY PREFERENCE PROTECTION & COMPROMISE GENERATOR REPORT")
    print("=" * 92)
    print(f"Total Groups Evaluated:       {demo_results['total_groups']}")
    print(f"Protection Triggered Share:   {demo_results['weighted_minority']['protection_triggered_share'] * 100:.1f}%")
    print(f"Soft Conflicts Resolved:      {demo_results['weighted_minority']['soft_conflicts_resolved_count']}")
    print(f"Unresolved Rejections Count:  {demo_results['weighted_minority']['unresolved_rejections_count']}")
    print("-" * 92)
    header_fmt = "{:<28} | {:<12} | {:<12} | {:<18} | {:<12}"
    row_fmt    = "{:<28} | {:<12} | {:<12} | {:<18} | {:<12}"
    print(header_fmt.format("Metric", "Pref-Only", "Weighted", "Weighted+Minority", "Union-All"))
    print("-" * 92)

    p = demo_results["preference_only"]
    w = demo_results["weighted"]
    m = demo_results["weighted_minority"]
    u = demo_results["union_all"]

    print(row_fmt.format("Mean Preference Coverage", f"{p['mean_coverage']:.4f}", f"{w['mean_coverage']:.4f}", f"{m['mean_coverage']:.4f}", f"{u['mean_coverage']:.4f}"))
    print(row_fmt.format("Mean Min Satisfaction", f"{p['mean_min_satisfaction']:.4f}", f"{w['mean_min_satisfaction']:.4f}", f"{m['mean_min_satisfaction']:.4f}", f"{u['mean_min_satisfaction']:.4f}"))
    print(row_fmt.format("Mean Satisfaction Gap", f"{p['mean_satisfaction_gap']:.4f}", f"{w['mean_satisfaction_gap']:.4f}", f"{m['mean_satisfaction_gap']:.4f}", f"{u['mean_satisfaction_gap']:.4f}"))
    print(row_fmt.format("Majority Satisfaction", f"{p['mean_majority_satisfaction']:.4f}", f"{w['mean_majority_satisfaction']:.4f}", f"{m['mean_majority_satisfaction']:.4f}", f"{u['mean_majority_satisfaction']:.4f}"))
    print(row_fmt.format("Mean Plan Size", f"{p['mean_plan_size']:.2f}", f"{w['mean_plan_size']:.2f}", f"{m['mean_plan_size']:.2f}", f"{u['mean_plan_size']:.2f}"))
    print("=" * 92)
    print("\nMETHODOLOGICAL NOTE:")
    print(f"  * {METHODOLOGICAL_NOTE}")
    print("=" * 92 + "\n")


if __name__ == "__main__":
    run_evaluation()
