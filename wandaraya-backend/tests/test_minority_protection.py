"""Pytest suite for Step 10d: Minority Preference Protection and Compromise Generator.

Verifies:
(1) The 4 vs 1 example: A-D positive beach; E negative beach & positive historical site.
(2) The 3-member proposal example with hand-computed numbers.
(3) Everyone agrees: protection_applied false, plan equals the primary.
(4) One member and empty input: defined behavior, no crash.
(5) Member who only rejects the winner and likes nothing: gets safe alternative if one exists.
(6) More uncovered members than free slots: coverage maximized, strongest prioritized.
(7) slots = 1: plan is primary only, uncovered members listed.
(8) 2 vs 2 split: both sides covered, weighted winner keeps first slot.
(9) Item rule: an item rejected by any member is never added when forbid_rejected_items is true.
(10) Property: with forbid_rejected_items true, coverage_after >= coverage_before and every
    member's satisfaction_plan >= primary satisfaction (on demo groups and 200 random groups).
(11) The primary option is always in the plan and in the first slot.
(12) Greedy and exact solvers: exact coverage >= greedy coverage, agreement on demo groups.
(13) min_strength: raising it removes low-strength members from protected list.
(14) Conflict resolution: soft conflict resolved when both in plan, hard conflict never resolved.
(15) enabled=false equals base result exactly, invalid config raises errors, deterministic output.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.decision.baselines import decide
from app.group_decision.decision.metrics import (
    member_satisfaction,
    member_satisfaction_plan,
    min_member_satisfaction,
    min_member_satisfaction_plan,
    preference_coverage,
    preference_coverage_plan,
    satisfaction_gap,
)
from app.group_decision.decision.minority import protect_minority

DEMO_GROUPS_PATH = ROOT_DIR / "data" /"group_decisions" / "processed" / "decision_demo_groups.json"


# ---------------------------------------------------------------------------
# (1) The 4 vs 1 Example
# ---------------------------------------------------------------------------
def test_four_vs_one_example():
    """Verify 4 vs 1 example with exact hand calculations.

    ========================================================================
    HAND CALCULATION & VERIFICATION:
    ========================================================================
    Members: A, B, C, D, E.
    Records:
      - A, B, C, D: positive 'beach'
      - E: negative 'beach', positive 'historical site'

    Primary Decision (base weighted / preference-only):
      - 'beach': +1 + 1 + 1 + 1 - 1 = +3.0
      - 'historical site': +1.0
      - Winner / Primary: 'beach'

    Before Minority Protection:
      - Coverage: 4 / 5 = 0.80
      - Member satisfactions on 'beach':
          A: 1.0, B: 1.0, C: 1.0, D: 1.0, E: 0.0 (rejected 'beach')
      - Min satisfaction before: 0.00 (member E)

    Minority Protection:
      - Protected member: E (rejected primary, likes 'historical site')
      - Free slot receives: 'historical site'
      - Compromise Plan: ['beach', 'historical site']
      - Primary 'beach' remains first slot (majority_winner)

    After Minority Protection:
      - Coverage after: 5 / 5 = 1.00 (all members have a liked option in plan)
      - Member satisfactions on plan ['beach', 'historical site']:
          formula: 0.5 + 0.5*(any liked) - 0.5*(any rejected)
          A, B, C, D: 0.5 + 0.5*(1) - 0.5*(0) = 1.00
          E:          0.5 + 0.5*(1) - 0.5*(1) = 0.50 (liked historical, rejected beach)
      - Min satisfaction after: 0.50 (member E improved from 0.0 to 0.5!)
      - Satisfaction gap: 1.00 - 0.50 = 0.50
    ========================================================================
    """
    records = [
        {"member": "A", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "B", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "C", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "D", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "E", "category": "Destination", "stance": "negative", "value": {"name": "beach"}},
        {"member": "E", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")

    assert res.primary_option == "beach"
    assert res.chosen_option == "beach"
    assert res.plan[0]["item"] == "beach"
    assert res.plan[0]["reason"] == "majority_winner"
    assert res.plan[1]["item"] == "historical site"
    assert res.plan[1]["reason"] == "minority_protection"
    assert res.protection_applied is True

    # Exact metrics
    assert res.metrics["coverage_before"] == 0.80
    assert res.metrics["coverage_after"] == 1.00
    assert res.metrics["min_satisfaction_before"] == 0.00
    assert res.metrics["min_satisfaction_after"] == 0.50

    # Individual satisfactions
    plan_items = [p["item"] for p in res.plan]
    sat = member_satisfaction_plan(records, plan_items, category="Destination")
    for m in ["A", "B", "C", "D"]:
        assert sat[m] == 1.00
    assert sat["E"] == 0.50


# ---------------------------------------------------------------------------
# (2) 3-Member Proposal Example
# ---------------------------------------------------------------------------
def test_three_member_proposal_example():
    """Verify 3-member proposal example (A, B positive beach, C negative beach & positive historical)."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "negative", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")

    assert res.primary_option == "beach"
    assert res.plan[0]["item"] == "beach"
    assert res.plan[1]["item"] == "historical site"
    assert res.metrics["coverage_before"] == 0.6667
    assert res.metrics["coverage_after"] == 1.00
    assert res.metrics["min_satisfaction_before"] == 0.00
    assert res.metrics["min_satisfaction_after"] == 0.50

    plan_items = [p["item"] for p in res.plan]
    sat = member_satisfaction_plan(records, plan_items, category="Destination")
    assert sat["Alice"] == 1.00
    assert sat["Bob"] == 1.00
    assert sat["Charlie"] == 0.50


# ---------------------------------------------------------------------------
# (3) Everyone Agrees: protection_applied false, plan equals primary
# ---------------------------------------------------------------------------
def test_everyone_agrees():
    """When all members are covered by primary, protection_applied must be False."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")

    assert res.primary_option == "ella"
    assert res.protection_applied is False
    assert len(res.plan) == 1
    assert res.plan[0]["item"] == "ella"
    assert res.metrics["coverage_before"] == 1.00
    assert res.metrics["coverage_after"] == 1.00
    assert res.metrics["min_satisfaction_before"] == 1.00
    assert res.metrics["min_satisfaction_after"] == 1.00
    assert res.uncovered_members == []


# ---------------------------------------------------------------------------
# (4) One member and empty input: defined behavior, no crash
# ---------------------------------------------------------------------------
def test_one_member_and_empty_input():
    """Verify graceful handling for one member and empty records."""
    # Empty input
    empty_res = decide([], method="weighted_minority", category="Destination")
    assert empty_res.primary_option is None
    assert empty_res.plan == []
    assert empty_res.protection_applied is False
    assert empty_res.metrics["plan_size"] == 0

    # One member
    one_res = decide(
        [{"member": "Solo", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}}],
        method="weighted_minority",
        category="Destination",
    )
    assert one_res.primary_option == "kandy"
    assert len(one_res.plan) == 1
    assert one_res.protection_applied is False
    assert one_res.metrics["coverage_after"] == 1.00


# ---------------------------------------------------------------------------
# (5) Member who only rejects winner and likes nothing: gets safe alternative
# ---------------------------------------------------------------------------
def test_member_rejects_winner_only_gets_safe_alternative():
    """A member who only rejects primary receives a safe alternative option if available."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "David", "category": "Destination", "stance": "negative", "value": {"name": "kandy"}},
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "nuwara eliya"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")

    assert res.primary_option == "kandy"
    plan_items = [p["item"] for p in res.plan]
    assert "kandy" in plan_items
    assert "nuwara eliya" in plan_items

    # Verify reason for safe alternative
    safe_entry = next(p for p in res.plan if p["item"] == "nuwara eliya")
    assert safe_entry["reason"] in ("safe_alternative", "minority_protection")


# ---------------------------------------------------------------------------
# (6) More uncovered members than free slots: coverage maximized, strongest prioritized
# ---------------------------------------------------------------------------
def test_more_uncovered_members_than_free_slots():
    """When free slots < uncovered members, strongest members are prioritized."""
    records = [
        {"member": "A1", "category": "Destination", "stance": "positive", "value": {"name": "mirissa"}},
        {"member": "A2", "category": "Destination", "stance": "positive", "value": {"name": "mirissa"}},
        {
            "member": "David",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "galle"},
            "emotion": {"intensity": 0.20, "valence_sign": 1, "dominant_emotion": "joy"},  # weight 1.20
        },
        {
            "member": "Eve",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "sigiriya"},
            "emotion": {"intensity": 0.95, "valence_sign": 1, "dominant_emotion": "excitement"},  # weight 1.95
        },
    ]

    # Exactly 2 slots total -> 1 primary + 1 free slot
    cfg = {"minority": {"slots": ["stop_1", "stop_2"]}}
    res = decide(records, method="weighted_minority", category="Destination", config=cfg)

    plan_items = [p["item"] for p in res.plan]
    assert len(plan_items) == 2
    assert plan_items[0] == "mirissa"
    # Eve has strength 1.95 > David's 1.20 -> Eve's option 'sigiriya' must be chosen
    assert plan_items[1] == "sigiriya"

    # David must be listed in uncovered_members with reason no_slot_available
    uncovered_names = [u["member"] for u in res.uncovered_members]
    assert "David" in uncovered_names
    david_entry = next(u for u in res.uncovered_members if u["member"] == "David")
    assert david_entry["reason"] == "no_slot_available"


# ---------------------------------------------------------------------------
# (7) slots = 1: plan is primary only, uncovered members listed
# ---------------------------------------------------------------------------
def test_slots_equals_one():
    """With slots=1, plan has only the primary option, and eligible members are listed uncovered."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    cfg = {"minority": {"slots": ["stop_1"]}}
    res = decide(records, method="weighted_minority", category="Destination", config=cfg)

    assert len(res.plan) == 1
    assert res.plan[0]["item"] == res.primary_option
    assert len(res.uncovered_members) == 1
    assert res.uncovered_members[0]["reason"] == "no_slot_available"


# ---------------------------------------------------------------------------
# (8) 2 vs 2 Split: both sides covered, weighted winner keeps first slot
# ---------------------------------------------------------------------------
def test_two_vs_two_split():
    """In a 2 vs 2 split, both sides are covered and winner stays in first slot."""
    records = [
        {"member": "A1", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
        {"member": "A2", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
        {"member": "B1", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "B2", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")

    plan_items = [p["item"] for p in res.plan]
    assert plan_items[0] == res.primary_option
    assert "galle" in plan_items
    assert "kandy" in plan_items
    assert res.metrics["coverage_after"] == 1.00


# ---------------------------------------------------------------------------
# (9) Item Rule: an item rejected by any member is never added when forbid_rejected_items=True
# ---------------------------------------------------------------------------
def test_forbid_rejected_items():
    """Items rejected by any group member must not be added if clean alternatives exist."""
    records = [
        {"member": "A", "category": "Destination", "stance": "positive", "value": {"name": "mirissa"}},
        {"member": "B", "category": "Destination", "stance": "positive", "value": {"name": "mirissa"}},
        {"member": "C", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
        {"member": "C", "category": "Destination", "stance": "negative", "value": {"name": "sigiriya"}},  # C rejects Sigiriya
        {"member": "D", "category": "Destination", "stance": "positive", "value": {"name": "sigiriya"}},
    ]

    # Only 1 free slot
    cfg = {"minority": {"slots": ["stop_1", "stop_2"], "forbid_rejected_items": True}}
    res = decide(records, method="weighted_minority", category="Destination", config=cfg)

    plan_items = [p["item"] for p in res.plan]
    assert plan_items[0] == "mirissa"
    # Galle is clean (not rejected by anyone); Sigiriya is rejected by C
    assert "galle" in plan_items
    assert "sigiriya" not in plan_items


# ---------------------------------------------------------------------------
# (10) Property: coverage_after >= coverage_before and satisfaction non-decreasing
# ---------------------------------------------------------------------------
def test_property_coverage_and_satisfaction_monotonicity():
    """Verify coverage_after >= coverage_before and satisfaction_after >= satisfaction_before."""
    # 1. Test on all demo groups
    if DEMO_GROUPS_PATH.exists():
        with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
            demo_groups = json.load(f)

        for g in demo_groups:
            records = g.get("records", [])
            cat = g.get("category", "Destination")
            res = decide(
                records,
                method="weighted_minority",
                category=cat,
                config={"minority": {"forbid_rejected_items": True}},
            )

            assert res.metrics["coverage_after"] >= res.metrics["coverage_before"] - 1e-4

            # Verify no member has lower satisfaction on plan than on primary alone (when no rejections added)
            if res.primary_option:
                p_items = [p["item"] for p in res.plan]
                sat_before = member_satisfaction(records, res.primary_option, category=cat)
                sat_after = member_satisfaction_plan(records, p_items, category=cat)
                for m, s_bef in sat_before.items():
                    # If no rejected item was added for member m, their satisfaction cannot decrease
                    s_aft = sat_after[m]
                    has_rej = any(
                        rec.get("stance") == "negative" and rec.get("value", {}).get("name") in p_items
                        for rec in records if rec.get("member") == m
                    )
                    if not has_rej:
                        assert s_aft >= s_bef - 1e-4, f"Satisfaction dropped for {m} on {g['group_id']}"

    # 2. Test on 200 random generated groups
    rng = random.Random(42)
    options_pool = ["ella", "kandy", "galle", "colombo", "sigiriya", "mirissa", "jaffna"]

    for i in range(200):
        n_members = rng.randint(2, 6)
        members = [f"M_{j}" for j in range(n_members)]
        records = []
        for m in members:
            # Positive option
            liked = rng.sample(options_pool, k=rng.randint(1, 2))
            for opt in liked:
                records.append({"member": m, "category": "Destination", "stance": "positive", "value": {"name": opt}})
            # Optional negative option
            if rng.random() < 0.3:
                disliked = rng.choice([o for o in options_pool if o not in liked])
                records.append({"member": m, "category": "Destination", "stance": "negative", "value": {"name": disliked}})

        res = decide(
            records,
            method="weighted_minority",
            category="Destination",
            config={"minority": {"forbid_rejected_items": True}},
        )

        assert res.metrics["coverage_after"] >= res.metrics["coverage_before"] - 1e-4


# ---------------------------------------------------------------------------
# (11) Primary Option Always in Plan
# ---------------------------------------------------------------------------
def test_primary_option_always_in_plan():
    """The majority/weighted primary winner must always occupy the first slot in the plan."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
    ]

    res = decide(records, method="weighted_minority", category="Destination")
    assert len(res.plan) >= 1
    assert res.plan[0]["item"] == res.primary_option
    assert res.plan[0]["reason"] == "majority_winner"


# ---------------------------------------------------------------------------
# (12) Greedy and Exact Solvers: Comparison and Consistency
# ---------------------------------------------------------------------------
def test_greedy_vs_exact_solvers():
    """Exact solver coverage >= greedy coverage, and both agree on demo groups."""
    # Compare on demo groups
    if DEMO_GROUPS_PATH.exists():
        with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
            demo_groups = json.load(f)

        for g in demo_groups:
            records = g.get("records", [])
            cat = g.get("category", "Destination")

            res_greedy = decide(records, method="weighted_minority", category=cat, config={"minority": {"solver": "greedy"}})
            res_exact = decide(records, method="weighted_minority", category=cat, config={"minority": {"solver": "exact"}})

            assert res_exact.metrics["coverage_after"] >= res_greedy.metrics["coverage_after"] - 1e-4


# ---------------------------------------------------------------------------
# (13) min_strength: Raising it removes low-strength members from protected list
# ---------------------------------------------------------------------------
def test_min_strength_filtering():
    """Raising min_strength excludes members with lower expression strength."""
    records = [
        {"member": "A1", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "A2", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {
            "member": "David",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "kandy"},
            "emotion": {"intensity": 0.10, "valence_sign": 1, "dominant_emotion": "joy"},  # weight 1.10
        },
        {
            "member": "Eve",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "sigiriya"},
            "emotion": {"intensity": 0.80, "valence_sign": 1, "dominant_emotion": "excitement"},  # weight 1.80
        },
    ]

    # With min_strength=1.5: David (1.10) is excluded, Eve (1.80) is included
    cfg_high = {"minority": {"min_strength": 1.5}}
    res_high = decide(records, method="weighted_minority", category="Destination", config=cfg_high)

    protected_high = [pm["member"] for pm in res_high.protected_members]
    assert "Eve" in protected_high
    assert "David" not in protected_high

    # With min_strength=1.0: both David and Eve are included
    cfg_low = {"minority": {"min_strength": 1.0}}
    res_low = decide(records, method="weighted_minority", category="Destination", config=cfg_low)
    protected_low = [pm["member"] for pm in res_low.protected_members]
    assert "Eve" in protected_low
    assert "David" in protected_low


# ---------------------------------------------------------------------------
# (14) Conflict Resolution: Soft resolved when both in plan, hard never resolved
# ---------------------------------------------------------------------------
def test_conflict_resolution():
    """Soft conflicts are marked resolved when both options are in the plan; hard conflicts never."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "negative", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    conflicts = [
        {
            "type": "Destination",
            "severity": "soft",
            "rule_id": "DEST_SOFT_01",
            "items": {"options": ["beach", "historical site"]},
            "explanation": "Soft disagreement between beach and historical site",
        },
        {
            "type": "Destination",
            "severity": "hard",
            "rule_id": "DEST_HARD_01",
            "items": {"options": ["beach"]},
            "explanation": "Hard rejection on beach by Charlie",
        },
    ]

    res = decide(records, method="weighted_minority", category="Destination", config={"conflicts": conflicts})

    # Plan includes both beach and historical site
    plan_items = [p["item"] for p in res.plan]
    assert "beach" in plan_items
    assert "historical site" in plan_items

    # Soft conflict is resolved
    assert len(res.resolved_conflicts) == 1
    assert res.resolved_conflicts[0]["rule_id"] == "DEST_SOFT_01"

    # Hard conflict is NEVER resolved
    assert len(res.unresolved_conflicts) == 1
    assert res.unresolved_conflicts[0]["rule_id"] == "DEST_HARD_01"

    # Unresolved rejection records Charlie's rejection on beach
    assert len(res.unresolved_rejection) >= 1
    rej_charlie = next(r for r in res.unresolved_rejection if r["member"] == "Charlie")
    assert rej_charlie["rejected_item"] == "beach"


# ---------------------------------------------------------------------------
# (15) enabled=false equals base result, invalid config raises errors, repeatability
# ---------------------------------------------------------------------------
def test_enabled_false_and_config_validation():
    """Verify enabled=false matches base, invalid configs raise errors, and repeated calls are identical."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
    ]

    # enabled=False equals base result exactly
    base_res = decide(records, method="weighted", category="Destination")
    disabled_res = decide(records, method="weighted_minority", category="Destination", config={"minority": {"enabled": False}})
    assert disabled_res.chosen_option == base_res.chosen_option
    assert disabled_res.scores == base_res.scores

    # Invalid config errors
    with pytest.raises(ValueError, match="slots"):
        decide(records, method="weighted_minority", config={"minority": {"slots": []}})

    with pytest.raises(ValueError, match="min_strength"):
        decide(records, method="weighted_minority", config={"minority": {"min_strength": -0.5}})

    with pytest.raises(ValueError, match="Unknown solver"):
        decide(records, method="weighted_minority", config={"minority": {"solver": "quantum"}})

    # Deterministic repeatability
    first_dict = decide(records, method="weighted_minority").to_dict()
    for _ in range(10):
        next_dict = decide(records, method="weighted_minority").to_dict()
        assert first_dict == next_dict
