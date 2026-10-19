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

DEMO_GROUPS_PATH = ROOT_DIR / "data" / "group_decision"/"processed" / "decision_demo_groups.json"


def run_demo(groups_path: Path | str = DEMO_GROUPS_PATH) -> None:
    """Run baseline decision methods on demo groups and display comparative table."""
    path = Path(groups_path)
    if not path.exists():
        print(f"Error: Demo groups file not found at {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        groups = json.load(f)

    print("\n" + "=" * 116)
    print("STEP 10a: DECISION ENGINE BASELINES DEMO (MAJORITY VS PREFERENCE-ONLY)")
    print("=" * 116)
    header_fmt = "{:<24} | {:<12} | {:<14} {:<6} {:<8} {:<8} | {:<16} {:<6} {:<8} {:<8}"
    row_fmt    = "{:<24} | {:<12} | {:<14} {:<6} {:<8.2f} {:<8.2f} | {:<16} {:<6} {:<8.2f} {:<8.2f}"
    
    print(header_fmt.format(
        "Group ID", "Category",
        "Maj: Winner", "Tie?", "Cov.", "MinSat",
        "Pref: Winner", "Tie?", "Cov.", "MinSat",
    ))
    print("-" * 116)

    for g in groups:
        gid = g.get("group_id", "GROUP")
        category = g.get("category", "Destination")
        records = g.get("records", [])

        # Majority
        maj_res = decide(records, method="majority", category=category)
        maj_chosen = maj_res.chosen_option or "None"
        maj_cov = preference_coverage(records, maj_res.chosen_option, category=category)
        maj_min_sat = min_member_satisfaction(records, maj_res.chosen_option, category=category)
        maj_tie_str = "YES" if maj_res.is_tie else "NO"

        # Preference-only
        pref_res = decide(records, method="preference_only", category=category)
        pref_chosen = pref_res.chosen_option or "None"
        pref_cov = preference_coverage(records, pref_res.chosen_option, category=category)
        pref_min_sat = min_member_satisfaction(records, pref_res.chosen_option, category=category)
        pref_tie_str = "YES" if pref_res.is_tie else "NO"

        # Shorten ID if needed
        short_id = gid.replace("GROUP_", "")[:24]

        print(row_fmt.format(
            short_id, category,
            maj_chosen[:14], maj_tie_str, maj_cov, maj_min_sat,
            pref_chosen[:16], pref_tie_str, pref_cov, pref_min_sat,
        ))

    print("=" * 116 + "\n")


if __name__ == "__main__":
    run_demo()
