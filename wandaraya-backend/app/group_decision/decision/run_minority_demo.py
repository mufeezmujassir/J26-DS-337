"""Demo runner for Minority Protection and Compromise Generator (Step 10d).

Loads example groups from data/processed/decision_demo_groups.json and displays
a side-by-side comparative table of:
1. Majority Voting
2. Preference-Only Aggregation
3. Emotion-Weighted Voting
4. Weighted + Minority Protection (Plan Skeleton, Coverage, and Min Satisfaction)
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.decision.baselines import decide
from app.group_decision.decision.metrics import min_member_satisfaction, preference_coverage
from app.group_decision.decision.minority import protect_minority

DEMO_GROUPS_PATH = ROOT_DIR / "data" /"group_decision" / "processed" / "decision_demo_groups.json"


def run_minority_demo(groups_path: Path | str = DEMO_GROUPS_PATH) -> None:
    """Print comparative decision table including minority compromise plans."""
    path = Path(groups_path)
    if not path.exists():
        print(f"Error: Demo groups file not found at {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        groups = json.load(f)

    print("\n" + "=" * 148)
    print("DECISION ENGINE: MAJORITY vs PREFERENCE-ONLY vs WEIGHTED vs WEIGHTED+MINORITY PROTECTION")
    print("=" * 148)
    header_fmt = "{:<24} | {:<12} | {:<10} | {:<10} | {:<10} | {:<28} | {:<7} | {:<7}"
    row_fmt    = "{:<24} | {:<12} | {:<10} | {:<10} | {:<10} | {:<28} | {:<7.2f} | {:<7.2f}"

    print(header_fmt.format(
        "Group ID", "Category",
        "Majority", "Pref-Only", "Weighted",
        "Compromise Plan", "PlanCov", "MinSat",
    ))
    print("-" * 148)

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # 1. Majority
        maj_res = decide(records, method="majority", category=category)
        maj_winner = maj_res.chosen_option or "None"

        # 2. Preference-only
        pref_res = decide(records, method="preference_only", category=category)
        pref_winner = pref_res.chosen_option or "None"

        # 3. Weighted
        wgt_res = decide(records, method="weighted", category=category)
        wgt_winner = wgt_res.chosen_option or "None"

        # 4. Weighted + Minority Protection
        min_res = decide(records, method="weighted_minority", category=category)
        plan_items = [p["item"] for p in min_res.plan]
        plan_str = ", ".join(plan_items) if plan_items else (min_res.chosen_option or "None")

        cov_after = min_res.metrics.get("coverage_after", 0.0)
        min_sat_after = min_res.metrics.get("min_satisfaction_after", 0.0)

        short_id = gid.replace("GROUP_", "")[:24]

        print(row_fmt.format(
            short_id, category,
            maj_winner[:10],
            pref_winner[:10],
            wgt_winner[:10],
            plan_str[:28],
            cov_after,
            min_sat_after,
        ))

    print("=" * 148 + "\n")


if __name__ == "__main__":
    run_minority_demo()
