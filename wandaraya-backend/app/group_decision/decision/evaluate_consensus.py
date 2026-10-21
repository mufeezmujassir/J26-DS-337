"""Evaluation script for Step 10e: Consensus Level and Fairness Metrics.

Compares five methods:
1. Majority Voting
2. Preference-Only Aggregation
3. Emotion-Weighted Voting
4. Weighted + Minority Protection (Compromise Plan Skeleton)
5. Naive 'Union-All' Baseline (includes all liked options)

Reports per method:
- Mean consensus level
- Mean min acceptance
- Mean satisfaction gap
- Mean Gini coefficient of acceptance
- Share of groups with consensus reached
- Qualitative label distribution (high, medium, low)
- Mean decision time in milliseconds
- Consensus satisfaction rate (min_acceptance >= 0.5 and level >= 0.75)

Statistical testing:
- Bootstrap 95% confidence intervals on paired differences (pref-only -> weighted -> weighted-minority)
- Wilcoxon signed-rank test ONLY when N >= 30; otherwise descriptive statistics only

Sensitivity analysis:
- Over lambda in {0.0, 0.25, 0.5, 0.75, 1.0}
- Over weight_by_vote_weight in {False, True}
- Over threshold variants (default, strict, lenient)
- Reports ranking stability across configurations

Saves outputs to:
- reports/consensus_results.json
- reports/figures/consensus_by_method.png
- reports/figures/consensus_sensitivity.png
- reports/figures/consensus_distribution.png

CRITICAL METHODOLOGICAL NOTE:
Consensus is partly by construction because the mechanism directly optimizes
the same acceptance measure. The custom dataset gold labels are synthetic, a higher
consensus level does not prove a better decision, and the real validation is the
blind user study, where participants' ratings should be compared against consensus_level.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.baselines import decide, set_seed
from app.group_decision.decision.consensus import compute_consensus, decide_with_consensus, load_consensus_config
from app.group_decision.decision.metrics import _deduplicate_records
from app.group_decision.decision.schemas import DecisionResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEMO_GROUPS_PATH = ROOT_DIR / "data" /"group_decision" / "processed" / "decision_demo_groups.json"
RESULTS_JSON_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "consensus_results.json"
BY_METHOD_FIG_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "figures" / "consensus_by_method.png"
SENSITIVITY_FIG_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "figures" / "consensus_sensitivity.png"
DISTRIBUTION_FIG_PATH = ROOT_DIR / "data"/"group_decision"/"reports" / "figures" / "consensus_distribution.png"

CANDIDATE_GOLD_PATHS = [
    ROOT_DIR / "data" / "processed" / "gold_preferences.json",
    ROOT_DIR / "data" / "processed" / "gold_structured_preferences.json",
    ROOT_DIR / "data" / "gold_preferences.json",
    ROOT_DIR / "data" / "group_decision" / "processed" / "gold_preferences.json",
]

METHODOLOGICAL_DISCLAIMER = (
    "Consensus is partly by construction because the mechanism optimizes the same "
    "acceptance measure. The custom dataset gold labels are synthetic, a higher "
    "consensus level does not prove a better decision, and the real validation is "
    "the blind user study, where participants' ratings should be compared against consensus_level."
)


def run_union_all_plan(records: list[Any], category: str) -> list[str]:
    """Naive baseline: include every distinct liked option in the plan."""
    member_stances = _deduplicate_records(records, category=category)
    liked_options: set[str] = set()
    for _, stances in member_stances.items():
        for opt, st in stances.items():
            if st == "positive":
                liked_options.add(opt)
    return sorted(list(liked_options))


def evaluate_dataset(
    groups: list[dict[str, Any]],
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all five decision methods across a dataset of groups."""
    total_groups = len(groups)
    if total_groups == 0:
        return {"total_groups": 0}

    methods = ["majority", "preference_only", "weighted", "weighted_minority", "union_all"]
    metrics_tracker: dict[str, dict[str, list[Any]]] = {
        m: {
            "level": [],
            "min_acc": [],
            "mean_acc": [],
            "gap": [],
            "gini": [],
            "reached": [],
            "label": [],
            "time_ms": [],
        }
        for m in methods
    }

    for g in groups:
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # Evaluate standard methods
        for m in ["majority", "preference_only", "weighted", "weighted_minority"]:
            t0 = time.perf_counter()
            res, cons = decide_with_consensus(
                records=records,
                method=m,
                config=config_overrides,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            cat_res = cons.categories.get(category)
            if cat_res:
                metrics_tracker[m]["level"].append(cat_res.consensus_level)
                metrics_tracker[m]["min_acc"].append(cat_res.min_acceptance)
                metrics_tracker[m]["mean_acc"].append(cat_res.mean_acceptance)
                metrics_tracker[m]["gap"].append(cat_res.satisfaction_gap)
                metrics_tracker[m]["gini"].append(cat_res.gini)
                metrics_tracker[m]["reached"].append(1 if cat_res.consensus_reached else 0)
                metrics_tracker[m]["label"].append(cat_res.level_label)
                metrics_tracker[m]["time_ms"].append(elapsed_ms)

        # Evaluate naive union_all baseline
        t0 = time.perf_counter()
        union_items = run_union_all_plan(records, category)
        primary = union_items[0] if union_items else None
        dummy_result = DecisionResult(
            category=category,
            chosen_option=primary,
            primary_option=primary,
            plan=[{"slot": f"slot_{i+1}", "item": it, "reason": "union_all"} for i, it in enumerate(union_items)],
            method="union_all",
            config=config_overrides or {},
        )
        union_cons = compute_consensus(records=records, result=dummy_result, config=config_overrides)
        union_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        u_cat = union_cons.categories.get(category)
        if u_cat:
            metrics_tracker["union_all"]["level"].append(u_cat.consensus_level)
            metrics_tracker["union_all"]["min_acc"].append(u_cat.min_acceptance)
            metrics_tracker["union_all"]["mean_acc"].append(u_cat.mean_acceptance)
            metrics_tracker["union_all"]["gap"].append(u_cat.satisfaction_gap)
            metrics_tracker["union_all"]["gini"].append(u_cat.gini)
            metrics_tracker["union_all"]["reached"].append(1 if u_cat.consensus_reached else 0)
            metrics_tracker["union_all"]["label"].append(u_cat.level_label)
            metrics_tracker["union_all"]["time_ms"].append(union_elapsed_ms)

    summary_per_method: dict[str, Any] = {}
    for m in methods:
        levels = metrics_tracker[m]["level"]
        min_accs = metrics_tracker[m]["min_acc"]
        mean_accs = metrics_tracker[m]["mean_acc"]
        gaps = metrics_tracker[m]["gap"]
        ginis = metrics_tracker[m]["gini"]
        reached_vals = metrics_tracker[m]["reached"]
        labels = metrics_tracker[m]["label"]
        times = metrics_tracker[m]["time_ms"]

        n = len(levels)
        if n == 0:
            continue

        label_counts = {lbl: labels.count(lbl) for lbl in ["high", "medium", "low"]}
        label_dist = {lbl: round(cnt / n, 4) for lbl, cnt in label_counts.items()}

        # Consensus satisfaction rate: min_acc >= 0.5 and level >= 0.75
        sat_rate_count = sum(1 for mi, lv in zip(min_accs, levels) if mi >= 0.50 and lv >= 0.75)
        consensus_sat_rate = round(sat_rate_count / n, 4)

        summary_per_method[m] = {
            "mean_consensus_level": round(float(np.mean(levels)), 4),
            "std_consensus_level": round(float(np.std(levels)), 4),
            "mean_min_acceptance": round(float(np.mean(min_accs)), 4),
            "mean_acceptance": round(float(np.mean(mean_accs)), 4),
            "mean_satisfaction_gap": round(float(np.mean(gaps)), 4),
            "mean_gini": round(float(np.mean(ginis)), 4),
            "share_consensus_reached": round(float(np.mean(reached_vals)), 4),
            "consensus_satisfaction_rate": consensus_sat_rate,
            "label_distribution": label_dist,
            "mean_decision_time_ms": round(float(np.mean(times)), 3),
        }

    return {
        "total_groups": total_groups,
        "summary": summary_per_method,
        "raw_metrics": metrics_tracker,
    }


def compute_bootstrap_paired_diff(
    x: list[float],
    y: list[float],
    n_boot: int = 2000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute mean paired difference (y - x) and 95% bootstrap confidence interval."""
    set_seed(seed)
    rng = np.random.default_rng(seed)
    diffs = np.array(y) - np.array(x)
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0, 0.0

    mean_diff = float(np.mean(diffs))
    boot_means = []
    for _ in range(n_boot):
        sample = rng.choice(diffs, size=n, replace=True)
        boot_means.append(float(np.mean(sample)))

    ci_low = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return round(mean_diff, 4), round(ci_low, 4), round(ci_high, 4)


def run_paired_statistical_tests(
    raw_metrics: dict[str, dict[str, list[Any]]],
    n_groups: int,
) -> dict[str, Any]:
    """Compute paired differences between consecutive methods and conditional Wilcoxon test."""
    pref_levels = raw_metrics["preference_only"]["level"]
    weighted_levels = raw_metrics["weighted"]["level"]
    minority_levels = raw_metrics["weighted_minority"]["level"]

    # 1. Pair 1: Weighted vs Preference-Only
    diff1_mean, diff1_low, diff1_high = compute_bootstrap_paired_diff(pref_levels, weighted_levels)

    # 2. Pair 2: Weighted+Minority vs Weighted
    diff2_mean, diff2_low, diff2_high = compute_bootstrap_paired_diff(weighted_levels, minority_levels)

    wilcoxon_results: dict[str, Any] = {}
    if n_groups >= 30:
        from scipy.stats import wilcoxon
        try:
            stat1, p1 = wilcoxon(weighted_levels, pref_levels)
            wilcoxon_results["weighted_vs_preference_only"] = {
                "statistic": float(stat1),
                "p_value": float(p1),
                "significant_p_05": bool(p1 < 0.05),
            }
        except Exception as e:
            wilcoxon_results["weighted_vs_preference_only"] = {"error": str(e)}

        try:
            stat2, p2 = wilcoxon(minority_levels, weighted_levels)
            wilcoxon_results["minority_vs_weighted"] = {
                "statistic": float(stat2),
                "p_value": float(p2),
                "significant_p_05": bool(p2 < 0.05),
            }
        except Exception as e:
            wilcoxon_results["minority_vs_weighted"] = {"error": str(e)}
    else:
        wilcoxon_results["note"] = (
            f"Wilcoxon signed-rank test omitted (N = {n_groups} < 30). "
            "Reporting descriptive statistics and bootstrap 95% CI only."
        )

    return {
        "consecutive_comparisons": {
            "weighted_minus_preference_only": {
                "mean_difference": diff1_mean,
                "bootstrap_95_ci": [diff1_low, diff1_high],
            },
            "minority_minus_weighted": {
                "mean_difference": diff2_mean,
                "bootstrap_95_ci": [diff2_low, diff2_high],
            },
        },
        "wilcoxon_test": wilcoxon_results,
    }


def run_sensitivity_analysis(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Test ranking stability over lambda, vote weighting, and thresholds."""
    lambdas = [0.0, 0.25, 0.50, 0.75, 1.0]
    weights_options = [False, True]
    threshold_variants = {
        "default": {"high_threshold": 0.75, "medium_threshold": 0.50, "reach_threshold": 0.75, "min_acceptance_threshold": 0.50},
        "strict": {"high_threshold": 0.80, "medium_threshold": 0.60, "reach_threshold": 0.80, "min_acceptance_threshold": 0.60},
        "lenient": {"high_threshold": 0.70, "medium_threshold": 0.40, "reach_threshold": 0.70, "min_acceptance_threshold": 0.40},
    }

    sensitivity_results: list[dict[str, Any]] = []
    base_ranking: list[str] = []

    for lam in lambdas:
        for w_opt in weights_options:
            for th_name, th_vals in threshold_variants.items():
                cfg: dict[str, Any] = {
                    "lambda": lam,
                    "weight_by_vote_weight": w_opt,
                    **th_vals,
                }
                eval_res = evaluate_dataset(groups, config_overrides=cfg)
                summary = eval_res["summary"]

                # Rank methods by mean consensus level descending
                ranking = sorted(
                    summary.keys(),
                    key=lambda m: summary[m]["mean_consensus_level"],
                    reverse=True,
                )

                if not base_ranking:
                    base_ranking = ranking

                is_same_as_base = (ranking == base_ranking)

                sensitivity_results.append({
                    "lambda": lam,
                    "weight_by_vote_weight": w_opt,
                    "threshold_variant": th_name,
                    "mean_levels": {m: summary[m]["mean_consensus_level"] for m in summary},
                    "ranking": ranking,
                    "ranking_matches_base": is_same_as_base,
                })

    all_rankings_match = all(r["ranking_matches_base"] for r in sensitivity_results)

    return {
        "base_ranking": base_ranking,
        "all_configurations_preserve_ranking": all_rankings_match,
        "configurations_tested": len(sensitivity_results),
        "results": sensitivity_results,
    }


def generate_plots(
    summary: dict[str, Any],
    sensitivity_data: dict[str, Any],
    raw_metrics: dict[str, dict[str, list[Any]]],
) -> None:
    """Generate and save the 3 required figures."""
    figures_dir = ROOT_DIR / "reports" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    methods = ["majority", "preference_only", "weighted", "weighted_minority", "union_all"]
    labels = ["Majority", "Pref-Only", "Weighted", "Weighted+Minority", "Union-All"]

    # --- FIGURE 1: consensus_by_method.png ---
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(methods))
    width = 0.25

    levels = [summary[m]["mean_consensus_level"] for m in methods]
    min_accs = [summary[m]["mean_min_acceptance"] for m in methods]
    gaps = [summary[m]["mean_satisfaction_gap"] for m in methods]

    r1 = ax.bar(x - width, levels, width, label="Consensus Level", color="#2b5c8f")
    r2 = ax.bar(x, min_accs, width, label="Min Acceptance", color="#38a169")
    r3 = ax.bar(x + width, gaps, width, label="Satisfaction Gap", color="#dd6b20")

    ax.set_ylabel("Score [0.0 - 1.0]", fontsize=12)
    ax.set_title("Step 10e: Consensus & Fairness Metrics Across Decision Methods", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0.0, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, fontsize=11)

    # Annotate bars
    for bars in [r1, r2, r3]:
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.2f}",
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(BY_METHOD_FIG_PATH, dpi=300)
    plt.close()
    logger.info("Saved figure: %s", BY_METHOD_FIG_PATH)

    # --- FIGURE 2: consensus_sensitivity.png ---
    fig, ax = plt.subplots(figsize=(10, 6))
    lambdas = [0.0, 0.25, 0.50, 0.75, 1.0]

    # Filter default sensitivity data across lambdas
    for m, lbl, color, marker in zip(
        methods,
        labels,
        ["#718096", "#3182ce", "#805ad5", "#dd6b20", "#38a169"],
        ["o", "s", "^", "D", "v"],
    ):
        m_levels = []
        for lam in lambdas:
            match = next(
                r for r in sensitivity_data["results"]
                if r["lambda"] == lam
                and not r["weight_by_vote_weight"]
                and r["threshold_variant"] == "default"
            )
            m_levels.append(match["mean_levels"][m])

        ax.plot(lambdas, m_levels, label=lbl, color=color, marker=marker, linewidth=2, markersize=8)

    ax.set_xlabel(r"Lambda parameter $\lambda$ (0 = Min Acceptance only, 1 = Mean Acceptance only)", fontsize=11)
    ax.set_ylabel("Mean Consensus Level", fontsize=11)
    ax.set_title(r"Step 10e: Sensitivity Analysis of Consensus Level over $\lambda$", fontsize=13, fontweight="bold")
    ax.set_xticks(lambdas)
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(frameon=True, fontsize=10)

    plt.tight_layout()
    plt.savefig(SENSITIVITY_FIG_PATH, dpi=300)
    plt.close()
    logger.info("Saved figure: %s", SENSITIVITY_FIG_PATH)

    # --- FIGURE 3: consensus_distribution.png ---
    fig, ax = plt.subplots(figsize=(10, 6))
    data_to_plot = [raw_metrics[m]["level"] for m in methods]

    bp = ax.boxplot(
        data_to_plot,
        tick_labels=labels,
        patch_artist=True,
        medianprops=dict(color="red", linewidth=2),
    )

    colors = ["#cbd5e0", "#bee3f8", "#d6bcfa", "#feebc8", "#c6f6d5"]
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)

    ax.set_ylabel("Consensus Level [0.0 - 1.0]", fontsize=12)
    ax.set_title("Distribution of Consensus Levels Across Demo Groups by Method", fontsize=13, fontweight="bold")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(DISTRIBUTION_FIG_PATH, dpi=300)
    plt.close()
    logger.info("Saved figure: %s", DISTRIBUTION_FIG_PATH)


def main() -> None:
    """Run full consensus evaluation pipeline and save reports."""
    print("\n" + "=" * 90)
    print("STEP 10e: CONSENSUS & FAIRNESS METRICS COMPREHENSIVE EVALUATION")
    print("=" * 90)

    # 1. Load Demo Groups
    if not DEMO_GROUPS_PATH.exists():
        logger.error("Demo groups file not found at %s", DEMO_GROUPS_PATH)
        sys.exit(1)

    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        demo_groups = json.load(f)

    # 2. Check for optional gold preferences dataset
    gold_groups: list[dict[str, Any]] = []
    for gpath in CANDIDATE_GOLD_PATHS:
        if gpath.exists():
            try:
                with open(gpath, "r", encoding="utf-8") as f:
                    gold_groups = json.load(f)
                logger.info("Found custom gold dataset at %s with %d groups.", gpath, len(gold_groups))
                break
            except Exception as e:
                logger.warning("Error reading %s: %s", gpath, e)

    eval_groups = demo_groups + gold_groups
    n_groups = len(eval_groups)
    print(f"Total groups evaluated: {n_groups} ({len(demo_groups)} demo + {len(gold_groups)} gold)")

    # 3. Primary Evaluation
    eval_results = evaluate_dataset(eval_groups)
    summary = eval_results["summary"]
    raw_metrics = eval_results["raw_metrics"]

    # 4. Statistical Testing
    stat_tests = run_paired_statistical_tests(raw_metrics, n_groups=n_groups)

    # 5. Sensitivity Analysis
    sensitivity = run_sensitivity_analysis(eval_groups)

    # 6. Generate Figures
    generate_plots(summary, sensitivity, raw_metrics)

    # 7. Print Comparative Table
    print("\n" + "-" * 110)
    print("{:<20} | {:<12} | {:<10} | {:<10} | {:<8} | {:<10} | {:<10} | {:<8}".format(
        "Method", "Cons. Level", "Min Acc", "Mean Acc", "Gap", "Gini", "Reached%", "Time(ms)"
    ))
    print("-" * 110)
    for m, s in summary.items():
        print("{:<20} | {:<12.4f} | {:<10.4f} | {:<10.4f} | {:<8.4f} | {:<10.4f} | {:<10.2%} | {:<8.2f}".format(
            m,
            s["mean_consensus_level"],
            s["mean_min_acceptance"],
            s["mean_acceptance"],
            s["mean_satisfaction_gap"],
            s["mean_gini"],
            s["share_consensus_reached"],
            s["mean_decision_time_ms"],
        ))
    print("-" * 110)

    print("\n--- Paired Differences (Bootstrap 95% Confidence Intervals) ---")
    p1 = stat_tests["consecutive_comparisons"]["weighted_minus_preference_only"]
    p2 = stat_tests["consecutive_comparisons"]["minority_minus_weighted"]
    print(f"Weighted vs Preference-Only : Mean diff = {p1['mean_difference']:+.4f}, 95% CI = {p1['bootstrap_95_ci']}")
    print(f"Minority vs Weighted        : Mean diff = {p2['mean_difference']:+.4f}, 95% CI = {p2['bootstrap_95_ci']}")

    if "note" in stat_tests["wilcoxon_test"]:
        print(f"\n[Statistical Test Status] {stat_tests['wilcoxon_test']['note']}")
    else:
        print(f"\n[Statistical Test Status] Wilcoxon p-values: {stat_tests['wilcoxon_test']}")

    print("\n--- Sensitivity & Ranking Stability ---")
    print(f"Base Method Ranking        : {sensitivity['base_ranking']}")
    print(f"Ranking Preserved All Tests: {sensitivity['all_configurations_preserve_ranking']}")

    # 8. Save Comprehensive Results JSON
    output_payload: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_groups": n_groups,
        "demo_groups_count": len(demo_groups),
        "gold_groups_count": len(gold_groups),
        "summary": summary,
        "statistical_tests": stat_tests,
        "sensitivity": {
            "base_ranking": sensitivity["base_ranking"],
            "all_configurations_preserve_ranking": sensitivity["all_configurations_preserve_ranking"],
            "configurations_tested": sensitivity["configurations_tested"],
        },
        "methodological_disclaimer": METHODOLOGICAL_DISCLAIMER,
    }

    RESULTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    print(f"\nSaved JSON results to {RESULTS_JSON_PATH}")
    print("\n" + "=" * 90)
    print("METHODOLOGICAL DISCLAIMER:")
    print(METHODOLOGICAL_DISCLAIMER)
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
