"""Demo runner for  Decision Engine Baselines.
a side-by-side comparative table of Majority Voting and Preference-Only aggregation.
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
from app.group_decision.decision.weighted import weighted_vote

DEMO_GROUPS_PATH = ROOT_DIR / "data" / "group_decision"/"processed" / "decision_demo_groups.json"


def run_demo(groups_path: Path | str = DEMO_GROUPS_PATH) -> None:
    """Run baseline decision methods on demo groups and display comparative table."""
    path = Path(groups_path)
    if not path.exists():
        print(f"Error: Demo groups file not found at {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        groups = json.load(f)

    print("\n" + "=" * 154)
    print("DECISION ENGINE DEMO: MAJORITY vs PREF-ONLY vs WEIGHTED vs WEIGHTED+MINORITY PROTECTION")
    print("=" * 154)
    header_fmt = "{:<24} | {:<12} | {:<10} {:<4} | {:<10} {:<4} | {:<10} {:<4} {:<4} | {:<24} | {:<7} {:<7}"
    row_fmt    = "{:<24} | {:<12} | {:<10} {:<4} | {:<10} {:<4} | {:<10} {:<4} {:<4} | {:<24} | {:<7.2f} {:<7.2f}"

    print(header_fmt.format(
        "Group ID", "Category",
         "Maj: Win", "Tie?",
        "Pref: Win", "Tie?",
        "Wgt: Win", "Tie?", "Flp?",
        "Minority Plan",
        "PlanCov", "MinSat",
    ))
    print("-" * 154)

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # Majority
        maj_res = decide(records, method="majority", category=category)
        maj_chosen = maj_res.chosen_option or "None"
        maj_tie_str = "Y" if maj_res.is_tie else "N"

        # Preference-only
        pref_res = decide(records, method="preference_only", category=category)
        pref_chosen = pref_res.chosen_option or "None"
        pref_tie_str = "Y" if pref_res.is_tie else "N"

         #  Weighted
        wgt_res = decide(records, method="weighted", category=category)
        wgt_chosen = wgt_res.chosen_option or "None"
        wgt_tie_str = "Y" if wgt_res.is_tie else "N"
        flip_str = "Y" if wgt_res.outcome_changed_vs_preference_only else "N"

        # 4. Minority Protection
        min_res = decide(records, method="weighted_minority", category=category)
        plan_items = [p["item"] for p in min_res.plan]
        plan_str = ", ".join(plan_items) if plan_items else (min_res.chosen_option or "None")
        cov_after = min_res.metrics.get("coverage_after", 0.0)
        min_sat_after = min_res.metrics.get("min_satisfaction_after", 0.0)

        # Shorten ID if needed
        short_id = gid.replace("GROUP_", "")[:24]

        print(row_fmt.format(
            short_id, category,
            maj_chosen[:10], maj_tie_str,
            pref_chosen[:10], pref_tie_str,
            wgt_chosen[:10], wgt_tie_str, flip_str,
            plan_str[:24],
            cov_after, min_sat_after,
        ))

    print("=" * 154 + "\n")


if __name__ == "__main__":
    run_demo()
