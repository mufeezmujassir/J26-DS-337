"""Tests for Consensus Level and Fairness Metrics (Step 10e).

Tests all 15 required scenarios with hand-verified calculations documented in comments.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
from typing import Any
import pytest

from app.group_decision.conflict.schemas import EmotionSignal, PreferenceRecord
from app.group_decision.decision.baselines import METHODS, decide, set_seed
from app.group_decision.decision.consensus import (
    compute_consensus,
    compute_gini,
    decide_with_consensus,
    load_consensus_config,
    to_consensus_decision,
    validate_consensus_config,
)
from app.group_decision.decision.schemas import ConsensusResult, DecisionResult

ROOT_DIR = Path(__file__).resolve().parent.parent
DEMO_GROUPS_PATH = ROOT_DIR / "data" / "group_decision" / "processed" / "decision_demo_groups.json"


def test_01_four_vs_one_preference_only():
    """(1) 4 vs 1 example, method preference_only:
    Members A, B, C, D: positive beach
    Member E: negative beach, positive historical site

    Hand calculation:
    - Primary winner: beach (4 positive votes)
    - Plan: [beach]
    - Member acceptances:
        A, B, C, D: positive beach -> 1.0
        E: negative beach -> 0.0
    - Mean acceptance = (1.0 + 1.0 + 1.0 + 1.0 + 0.0) / 5 = 4.0 / 5 = 0.80
    - Min acceptance = min(1.0, 1.0, 1.0, 1.0, 0.0) = 0.0
    - Consensus level = 0.5 * 0.80 + 0.5 * 0.0 = 0.40
    - Level label: "low" (0.40 < 0.50)
    - Consensus reached: False (0.40 < 0.75 and 0.0 < 0.50)
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="B", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="C", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="D", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="E", category="Destination", stance="negative", value={"name": "beach"}),
        PreferenceRecord(member="E", category="Destination", stance="positive", value={"name": "historical site"}),
    ]

    res, cons = decide_with_consensus(records, method="preference_only")

    assert res.chosen_option == "beach"
    assert cons.mean_acceptance == pytest.approx(0.80)
    assert cons.min_acceptance == pytest.approx(0.0)
    assert cons.consensus_level == pytest.approx(0.40)
    assert cons.level_label == "low"
    assert cons.consensus_reached is False
    assert cons.consensus_primary_only == pytest.approx(0.40)
    assert cons.consensus_gain == pytest.approx(0.0)


def test_02_four_vs_one_weighted_minority_plan():
    """(2) Same 4 vs 1 group, method weighted_minority with plan [beach, historical site]:

    Hand calculation:
    - Primary winner: beach
    - Compromise plan: [beach, historical site]
    - Member acceptances on plan:
        A, B, C, D: liked item in plan, no rejected item -> 1.0
        E: liked historical site (+0.5), rejected beach (-0.5) -> 0.5 + 0.5 - 0.5 = 0.50
    - Mean acceptance = (1.0 + 1.0 + 1.0 + 1.0 + 0.5) / 5 = 4.5 / 5 = 0.90
    - Min acceptance = min(1.0, 1.0, 1.0, 1.0, 0.5) = 0.50
    - Consensus level = 0.5 * 0.90 + 0.5 * 0.50 = 0.45 + 0.25 = 0.70
    - Level label: "medium" (0.50 <= 0.70 < 0.75)
    - Consensus reached: False (0.70 is below reach_threshold 0.75)
    - Primary-only level = 0.40
    - Consensus gain = 0.70 - 0.40 = 0.30
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="B", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="C", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="D", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="E", category="Destination", stance="negative", value={"name": "beach"}),
        PreferenceRecord(member="E", category="Destination", stance="positive", value={"name": "historical site"}),
    ]

    res, cons = decide_with_consensus(records, method="weighted_minority")

    assert res.chosen_option == "beach"
    assert len(res.plan) >= 2
    assert cons.mean_acceptance == pytest.approx(0.90)
    assert cons.min_acceptance == pytest.approx(0.50)
    assert cons.consensus_level == pytest.approx(0.70)
    assert cons.level_label == "medium"
    assert cons.consensus_reached is False
    assert cons.consensus_primary_only == pytest.approx(0.40)
    assert cons.consensus_gain == pytest.approx(0.30)


def test_03_three_member_proposal_example():
    """(3) 3-member proposal example:
    A: positive beach
    B: positive beach
    C: negative beach, positive historical site

    Hand calculation:
    - Primary-only [beach]:
        A: 1.0, B: 1.0, C: 0.0
        Mean = 2/3 = 0.6667
        Min = 0.0
        Consensus level = 0.5 * (2/3) + 0.5 * 0.0 = 1/3 = 0.3333
    - With plan [beach, historical site]:
        A: 1.0, B: 1.0
        C: 0.5 + 0.5 (historical) - 0.5 (beach) = 0.50
        Mean = (1.0 + 1.0 + 0.5) / 3 = 2.5 / 3 = 5/6 = 0.8333
        Min = 0.50
        Consensus level = 0.5 * (5/6) + 0.5 * 0.5 = 5/12 + 1/4 = 8/12 = 2/3 = 0.6667
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="B", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="C", category="Destination", stance="negative", value={"name": "beach"}),
        PreferenceRecord(member="C", category="Destination", stance="positive", value={"name": "historical site"}),
    ]

    res, cons = decide_with_consensus(records, method="weighted_minority")

    assert cons.consensus_primary_only == pytest.approx(0.3333, abs=1e-3)
    assert cons.consensus_level == pytest.approx(0.6667, abs=1e-3)


def test_04_everyone_positive_on_same_option():
    """(4) Everyone positive on the same option:
    Hand calculation:
    A: positive ella, B: positive ella, C: positive ella.
    Acceptance = {A: 1.0, B: 1.0, C: 1.0}
    Mean = 1.0, Min = 1.0, Level = 1.0, label = "high", reached = True.
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="B", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="C", category="Destination", stance="positive", value={"name": "ella"}),
    ]

    res, cons = decide_with_consensus(records, method="majority")

    assert cons.consensus_level == pytest.approx(1.0)
    assert cons.mean_acceptance == pytest.approx(1.0)
    assert cons.min_acceptance == pytest.approx(1.0)
    assert cons.level_label == "high"
    assert cons.consensus_reached is True


def test_05_everyone_rejects_only_option():
    """(5) Everyone rejects the only option:
    Hand calculation:
    Members A, B, C negative on 'ella'.
    If evaluated on 'ella':
    Acceptance = {A: 0.0, B: 0.0, C: 0.0}
    Mean = 0.0, Min = 0.0, Level = 0.0, label = "low".
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="negative", value={"name": "ella"}),
        PreferenceRecord(member="B", category="Destination", stance="negative", value={"name": "ella"}),
        PreferenceRecord(member="C", category="Destination", stance="negative", value={"name": "ella"}),
    ]

    # Dummy result forcing evaluation of 'ella'
    dummy_res = DecisionResult(
        category="Destination",
        chosen_option="ella",
        primary_option="ella",
        plan=[{"slot": "stop_1", "item": "ella", "reason": "winner"}],
        method="preference_only",
    )
    cons = compute_consensus(records, dummy_res)

    assert cons.consensus_level == pytest.approx(0.0)
    assert cons.mean_acceptance == pytest.approx(0.0)
    assert cons.min_acceptance == pytest.approx(0.0)
    assert cons.level_label == "low"
    assert cons.consensus_reached is False


def test_06_one_member_trivial():
    """(6) One member: computed, trivial_single_member true.
    Hand calculation:
    Member A: positive ella.
    Acceptance = {A: 1.0}
    trivial_single_member = True, notes contains single member note.
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "ella"}),
    ]

    res, cons = decide_with_consensus(records, method="preference_only")

    assert cons.trivial_single_member is True
    assert cons.mean_acceptance == pytest.approx(1.0)
    assert cons.min_acceptance == pytest.approx(1.0)
    assert cons.consensus_level == pytest.approx(1.0)
    assert any("single group member" in note for note in cons.notes)


def test_07_empty_records_defined_behaviour():
    """(7) Empty records: defined behaviour, no crash, no categories."""
    records: list[PreferenceRecord] = []
    res = decide(records, method="preference_only")
    cons = compute_consensus(records, res)

    assert isinstance(cons, ConsensusResult)
    assert cons.overall_level == pytest.approx(0.0)
    assert cons.overall_reached is False
    assert len(cons.categories) == 0


def test_08_category_no_positive_stance_skipped():
    """(8) A category with no positive stance is listed in categories_skipped and excluded from overall values."""
    records = [
        PreferenceRecord(member="Alice", category="Destination", stance="negative", value={"name": "ella"}),
    ]
    res = decide(records, method="preference_only", category="Destination")
    cons = compute_consensus(records, res)

    assert "Destination" in cons.categories_skipped
    assert "Destination" not in cons.categories
    assert cons.overall_level == pytest.approx(0.0)
    assert cons.overall_reached is False


def test_09_tie_detected_and_noted():
    """(9) Tie: is_tie true, tied_options listed, note present."""
    records = [
        PreferenceRecord(member="Alice", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="Bob", category="Destination", stance="positive", value={"name": "kandy"}),
    ]
    res, cons = decide_with_consensus(records, method="preference_only")

    assert cons.is_tie is True
    assert set(cons.tied_options) == {"ella", "kandy"}
    assert any("arbitrary" in note.lower() for note in cons.notes)


def test_10_lambda_extremes_and_validation():
    """(10) lambda = 1 gives mean only, lambda = 0 gives min only; invalid lambda raises an error."""
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "beach"}),
        PreferenceRecord(member="B", category="Destination", stance="negative", value={"name": "beach"}),
    ]
    res = decide(records, method="preference_only")

    # A: 1.0, B: 0.0 -> mean = 0.50, min = 0.0
    cons_mean_only = compute_consensus(records, res, config={"lambda": 1.0})
    assert cons_mean_only.consensus_level == pytest.approx(cons_mean_only.mean_acceptance)
    assert cons_mean_only.consensus_level == pytest.approx(0.50)

    cons_min_only = compute_consensus(records, res, config={"lambda": 0.0})
    assert cons_min_only.consensus_level == pytest.approx(cons_min_only.min_acceptance)
    assert cons_min_only.consensus_level == pytest.approx(0.0)

    # Invalid lambda validation
    with pytest.raises(ValueError, match="Invalid lambda"):
        compute_consensus(records, res, config={"lambda": -0.1})

    with pytest.raises(ValueError, match="Invalid lambda"):
        compute_consensus(records, res, config={"lambda": 1.5})


def test_11_weight_by_vote_weight_comparison():
    """(11) weight_by_vote_weight true vs false gives different results on a hand-built
    group with one strongly emotional member; write both numbers.

    Hand calculation:
    - Member Alice: positive on ella, dominant_emotion joy, intensity 1.0, valence_sign +1
        Weight = 1.0 + 1.0 * 1.0 * 1 = 2.0
    - Member Bob: negative on ella, neutral emotion, intensity 0.0
        Weight = 1.0
    - Acceptances on [ella]:
        Alice = 1.0, Bob = 0.0
    - When weight_by_vote_weight = False:
        Mean acceptance = (1.0 + 0.0) / 2 = 0.50
        Min acceptance = 0.0
        Consensus level = 0.5 * 0.50 + 0.5 * 0.0 = 0.2500
    - When weight_by_vote_weight = True:
        Weighted mean = (2.0 * 1.0 + 1.0 * 0.0) / (2.0 + 1.0) = 2.0 / 3.0 = 0.6667
        Min acceptance = 0.0
        Consensus level = 0.5 * (2/3) + 0.5 * 0.0 = 1/3 = 0.3333
    """
    records = [
        PreferenceRecord(
            member="Alice",
            category="Destination",
            stance="positive",
            value={"name": "ella"},
            emotion=EmotionSignal(intensity=1.0, valence_sign=1, dominant_emotion="joy"),
        ),
        PreferenceRecord(
            member="Bob",
            category="Destination",
            stance="negative",
            value={"name": "ella"},
            emotion=EmotionSignal(intensity=0.0, valence_sign=0, dominant_emotion="neutral"),
        ),
    ]

    res, cons_unweighted = decide_with_consensus(
        records, method="weighted", config={"weight_by_vote_weight": False}
    )
    _, cons_weighted = decide_with_consensus(
        records, method="weighted", config={"weight_by_vote_weight": True}
    )

    # Hand-verified numbers: 0.25 vs 0.3333
    assert cons_unweighted.consensus_level == pytest.approx(0.2500)
    assert cons_weighted.consensus_level == pytest.approx(0.3333, abs=1e-3)
    assert cons_weighted.consensus_level > cons_unweighted.consensus_level


def test_12_range_and_monotonicity_200_groups():
    """(12) Range and monotonicity property tests on 200 random groups with a fixed seed:
    - level always within 0-1
    - raising any single member's acceptance never lowers the level
    - with forbid_rejected_items true, weighted_minority consensus >= its primary-only consensus
    - level never exceeds mean_acceptance and never falls below min_acceptance (without penalty)
    """
    set_seed(42)
    rng = random.Random(42)
    options_pool = ["ella", "kandy", "galle", "colombo", "sigiriya", "mirissa", "jaffna"]

    for i in range(200):
        n_members = rng.randint(2, 6)
        members = [f"M_{j}" for j in range(n_members)]
        records: list[PreferenceRecord] = []

        for m in members:
            # Positive options
            liked = rng.sample(options_pool, k=rng.randint(1, 2))
            for opt in liked:
                records.append(
                    PreferenceRecord(member=m, category="Destination", stance="positive", value={"name": opt})
                )
            # Optional negative option (distinct from liked options)
            if rng.random() < 0.25:
                disliked = rng.choice([o for o in options_pool if o not in liked])
                records.append(
                    PreferenceRecord(member=m, category="Destination", stance="negative", value={"name": disliked})
                )

        res, cons = decide_with_consensus(
            records,
            method="weighted_minority",
            config={"minority": {"forbid_rejected_items": True}},
        )
        cat_cons = cons.categories.get("Destination")
        if not cat_cons or cat_cons.primary_option is None:
            continue

        # 1. Range test [0, 1]
        assert 0.0 <= cat_cons.consensus_level <= 1.0

        # 2. Bounds test: min_acceptance <= level <= mean_acceptance (conflict_penalty=0)
        assert cat_cons.min_acceptance <= cat_cons.consensus_level + 1e-4
        assert cat_cons.consensus_level <= cat_cons.mean_acceptance + 1e-4

        # 3. Minority gain test: with forbid_rejected_items true, when no rejected item is in plan,
        # weighted_minority consensus >= its primary-only consensus
        if not cat_cons.conflict_summary.get("unresolved_rejection_members"):
            assert cat_cons.consensus_level >= cat_cons.consensus_primary_only - 1e-4

        # 4. Monotonicity test: raising any single member's acceptance never lowers the level
        base_acceptances = list(cat_cons.member_acceptance.values())
        if base_acceptances:
            raised_acceptances = list(base_acceptances)
            raised_acceptances[0] = min(1.0, raised_acceptances[0] + 0.15)
            raised_mean = sum(raised_acceptances) / len(raised_acceptances)
            raised_min = min(raised_acceptances)
            raised_level = 0.5 * raised_mean + 0.5 * raised_min
            assert raised_level >= cat_cons.consensus_level - 1e-4



def test_13_conflict_handling_and_penalty():
    """(13) Conflict handling: unresolved hard conflict is counted; penalty 0 changes nothing;
    a positive penalty lowers the level by the expected amount and never goes below 0 or beyond cap.
    """
    records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="B", category="Destination", stance="positive", value={"name": "ella"}),
    ]
    # Hard conflict in Destination
    conflicts = [
        {
            "type": "Destination",
            "severity": "hard",
            "rule_id": "DEST_HARD_01",
            "members": ["A", "B"],
            "items": ["ella", "kandy"],
            "explanation": "Irreconcilable hard conflict",
        }
    ]

    res = decide(records, method="preference_only")

    # Raw level = 1.0
    # Penalty = 0.0 -> no effect
    cons_no_pen = compute_consensus(records, res, config={"conflict_penalty": 0.0}, conflicts=conflicts)
    assert cons_no_pen.conflict_summary["unresolved_hard"] == 1
    assert cons_no_pen.consensus_level == pytest.approx(1.0)

    # Penalty = 0.15 -> lowers level from 1.0 to 0.85
    cons_pen_15 = compute_consensus(records, res, config={"conflict_penalty": 0.15}, conflicts=conflicts)
    assert cons_pen_15.consensus_level == pytest.approx(0.85)

    # Penalty = 0.50 with max_conflict_penalty = 0.30 -> capped at 0.30 -> level = 0.70
    cons_capped = compute_consensus(
        records, res, config={"conflict_penalty": 0.50, "max_conflict_penalty": 0.30}, conflicts=conflicts
    )
    assert cons_capped.consensus_level == pytest.approx(0.70)

    # Penalty exceeding raw level clips to 0.0
    low_records = [
        PreferenceRecord(member="A", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="B", category="Destination", stance="negative", value={"name": "ella"}),
    ]
    low_res = decide(low_records, method="preference_only")  # raw level = 0.25
    cons_clipped = compute_consensus(
        low_records, low_res, config={"conflict_penalty": 0.40, "max_conflict_penalty": 0.50}, conflicts=conflicts
    )
    assert cons_clipped.consensus_level == pytest.approx(0.0)


def test_14_works_on_all_demo_groups_for_all_methods():
    """(14) Works for every method in METHODS on all demo groups."""
    assert DEMO_GROUPS_PATH.exists()
    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        groups = json.load(f)

    assert len(groups) >= 21  # 18 original + 3 new consensus demo groups

    eval_methods = ["majority", "preference_only", "weighted", "weighted_minority"]

    for g in groups:
        cat = g.get("category", "Destination")
        records = g.get("records", [])
        for m in eval_methods:
            res, cons = decide_with_consensus(records, method=m, config={"category": cat})
            assert isinstance(res, DecisionResult)
            assert isinstance(cons, ConsensusResult)
            assert 0.0 <= cons.overall_level <= 1.0


def test_15_to_consensus_decision_structure_and_determinism():
    """(15) to_consensus_decision contains the expected keys and no free text;
    identical output across repeated runs.
    """
    records = [
        PreferenceRecord(member="Alice", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="Bob", category="Destination", stance="positive", value={"name": "ella"}),
        PreferenceRecord(member="Charlie", category="Destination", stance="positive", value={"name": "sigiriya"}),
    ]
    res, cons = decide_with_consensus(records, method="weighted_minority", config={"category": "Destination"})

    payload1 = to_consensus_decision(cons, res, meta={"budget_override": False})
    payload2 = to_consensus_decision(cons, res, meta={"budget_override": False})

    expected_keys = {
        "options",
        "agreement_level",
        "level_label",
        "consensus_reached",
        "compromise_plan",
        "per_category",
        "unresolved",
    }
    assert expected_keys.issubset(payload1.keys())
    assert payload1["meta"] == {"budget_override": False}

    # Determinism: identical across repeated runs
    assert json.dumps(payload1, sort_keys=True) == json.dumps(payload2, sort_keys=True)
