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

    print("\n" + "=" * 140)
    print("DECISION ENGINE DEMO: MAJORITY vs PREFERENCE-ONLY vs EMOTION-WEIGHTED VOTING")
    print("=" * 140)
    header_fmt = "{:<24} | {:<12} | {:<13} {:<5} | {:<13} {:<5} | {:<13} {:<5} {:<6} | {:<7} {:<7}"
    row_fmt    = "{:<24} | {:<12} | {:<13} {:<5} | {:<13} {:<5} | {:<13} {:<5} {:<6} | {:<7.2f} {:<7.2f}"

    print(header_fmt.format(
        "Group ID", "Category",
        "Maj: Winner", "Tie?", 
        "Pref: Winner", "Tie?",
        "Wgt: Winner", "Tie?", "Flip?",
        "WgtCov", "WgtMinSat",
    ))
    print("-" * 140)

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # Majority
        maj_res = decide(records, method="majority", category=category)
        maj_chosen = maj_res.chosen_option or "None"
        maj_tie_str = "YES" if maj_res.is_tie else "NO"

        # Preference-only
        pref_res = decide(records, method="preference_only", category=category)
        pref_chosen = pref_res.chosen_option or "None"
        pref_tie_str = "YES" if pref_res.is_tie else "NO"

         #  Weighted
        wgt_res = decide(records, method="weighted", category=category)
        wgt_chosen = wgt_res.chosen_option or "None"
        wgt_tie_str = "YES" if wgt_res.is_tie else "NO"
        flip_str = "YES" if wgt_res.outcome_changed_vs_preference_only else "NO"
        wgt_cov = preference_coverage(records, wgt_res.chosen_option, category=category)
        wgt_min_sat = min_member_satisfaction(records, wgt_res.chosen_option, category=category)


        # Shorten ID if needed
        short_id = gid.replace("GROUP_", "")[:24]

        print(row_fmt.format(
            short_id, category,
            maj_chosen[:13], maj_tie_str,
            pref_chosen[:13], pref_tie_str,
            wgt_chosen[:13], wgt_tie_str, flip_str,
            wgt_cov, wgt_min_sat,
        ))

    print("=" * 140 + "\n")


if __name__ == "__main__":
    run_demo()
