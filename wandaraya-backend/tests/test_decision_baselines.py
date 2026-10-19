"""Pytest suite for Step 10a: Decision Engine Baselines (WANDARAYA Component 3).

Verifies majority voting and preference-only aggregation across:
(1) Proposal example (A positive beach, B positive beach, C negative beach & positive historical)
(2) Minority example (4 positive beach, 1 negative beach & positive historical site)
(3) Differing choices between majority and preference-only
(4) Edge cases: ties, one member, empty input, no positives, split vs latest policy,
    negative_veto on/off, synonym normalization, duplicate records, invalid stance,
    and deterministic repeatability.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.decision.baselines import decide, majority_vote, preference_only
from app.group_decision.decision.metrics import (
    member_satisfaction,
    min_member_satisfaction,
    preference_coverage,
)


# ---------------------------------------------------------------------------
# (1) Proposal Example
# ---------------------------------------------------------------------------
def test_proposal_example():
    """Proposal example:

    A: positive beach
    B: positive beach
    C: negative beach, positive historical site
    """
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "negative", "value": {"name": "beach"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    # Majority Voting
    maj_res = decide(records, method="majority", category="Destination")
    # Alice: beach (1.0), Bob: beach (1.0), Charlie: historical site (1.0)
    assert maj_res.scores["beach"] == 2.0
    assert maj_res.scores["historical site"] == 1.0
    assert maj_res.chosen_option == "beach"
    assert maj_res.is_tie is False
    assert maj_res.tied_options == []
    # Total votes = 3.0. Beach share = 2/3 = 0.6667 > 0.5 -> has_majority is True
    assert maj_res.has_majority is True

    # Preference-Only (negative_veto=False)
    pref_res = decide(records, method="preference_only", category="Destination", config={"negative_veto": False})
    # Beach score: Alice (+1) + Bob (+1) + Charlie (-1) = 1.0
    # Historical site score: Charlie (+1) + Alice (0) + Bob (0) = 1.0
    assert pref_res.scores["beach"] == 1.0
    assert pref_res.scores["historical site"] == 1.0
    # Both share top score of 1.0 -> tie!
    assert pref_res.is_tie is True
    assert set(pref_res.tied_options) == {"beach", "historical site"}
    # Deterministic alphabetical tie-break picks "beach"
    assert pref_res.chosen_option == "beach"

    # Preference-Only with negative_veto=True
    # Charlie rejected beach -> beach is vetoed, historical site wins
    pref_veto_res = decide(records, method="preference_only", category="Destination", config={"negative_veto": True})
    assert pref_veto_res.chosen_option == "historical site"
    assert pref_veto_res.is_tie is False


# ---------------------------------------------------------------------------
# (2) Minority Example from Proposal
# ---------------------------------------------------------------------------
def test_minority_proposal_example():
    """Minority example from proposal:

    Four members positive beach, one member negative beach and positive historical site.
    Both methods choose beach, coverage is 0.8, and minority member's satisfaction is 0.0.
    Documents why minority protection is needed in later steps.
    """
    records = [
        {"member": "M1", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "M2", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "M3", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "M4", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "M5", "category": "Destination", "stance": "negative", "value": {"name": "beach"}},
        {"member": "M5", "category": "Destination", "stance": "positive", "value": {"name": "historical site"}},
    ]

    maj_res = decide(records, method="majority", category="Destination")
    pref_res = decide(records, method="preference_only", category="Destination")

    # Both methods choose beach
    assert maj_res.chosen_option == "beach"
    assert pref_res.chosen_option == "beach"

    # Coverage is 4 out of 5 members = 0.8
    cov = preference_coverage(records, "beach", category="Destination")
    assert cov == 0.8

    # Minority member satisfaction is 0.0
    sat = member_satisfaction(records, "beach", category="Destination")
    assert sat["M1"] == 1.0
    assert sat["M2"] == 1.0
    assert sat["M3"] == 1.0
    assert sat["M4"] == 1.0
    assert sat["M5"] == 0.0  # Rejected beach

    # Min member satisfaction across the group is 0.0
    min_sat = min_member_satisfaction(records, "beach", category="Destination")
    assert min_sat == 0.0


# ---------------------------------------------------------------------------
# (3) Differing Choices Between Majority and Preference-Only
# ---------------------------------------------------------------------------
def test_majority_vs_preference_only_divergence():
    """Scenario with rejections where majority voting and preference-only pick different winners.

    M1, M2, M3: positive on Sigiriya
    M4, M5: negative on Sigiriya, positive on Galle
    M1, M2, M3: neutral on Galle
    Majority: Sigiriya (3 votes) vs Galle (2 votes) -> Sigiriya wins.
    Preference-only: Sigiriya score = 3 - 2 = 1. Galle score = 2 + 0 = 2 -> Galle wins.
    """
    records = [
        {"member": "M1", "category": "Destination", "stance": "positive", "value": {"name": "sigiriya"}},
        {"member": "M2", "category": "Destination", "stance": "positive", "value": {"name": "sigiriya"}},
        {"member": "M3", "category": "Destination", "stance": "positive", "value": {"name": "sigiriya"}},
        {"member": "M4", "category": "Destination", "stance": "negative", "value": {"name": "sigiriya"}},
        {"member": "M5", "category": "Destination", "stance": "negative", "value": {"name": "sigiriya"}},
        {"member": "M4", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
        {"member": "M5", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
    ]

    maj_res = decide(records, method="majority", category="Destination")
    pref_res = decide(records, method="preference_only", category="Destination")

    assert maj_res.chosen_option == "sigiriya"
    assert pref_res.chosen_option == "galle"
    assert maj_res.chosen_option != pref_res.chosen_option


# ---------------------------------------------------------------------------
# (4) Ties and Tie-Breaks
# ---------------------------------------------------------------------------
def test_tie_case_and_tie_break_policies():
    """Verify tie detection, tied_options list, and alphabetical vs first_mentioned tie-breaks."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
    ]

    # Alphabetical tie-break: "ella" < "kandy"
    res_alpha = decide(records, method="majority", config={"tie_break": "alphabetical"})
    assert res_alpha.is_tie is True
    assert set(res_alpha.tied_options) == {"ella", "kandy"}
    assert res_alpha.chosen_option == "ella"

    # First mentioned tie-break: "kandy" was mentioned first by Alice
    res_first = decide(records, method="majority", config={"tie_break": "first_mentioned"})
    assert res_first.is_tie is True
    assert res_first.chosen_option == "kandy"


# ---------------------------------------------------------------------------
# (5) One Member and Empty Input
# ---------------------------------------------------------------------------
def test_one_member():
    """Single member with positive option wins unanimously."""
    records = [
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
    ]
    res_maj = decide(records, method="majority", category="Activity")
    assert res_maj.chosen_option == "hiking"
    assert res_maj.has_majority is True
    assert res_maj.is_tie is False

    res_pref = decide(records, method="preference_only", category="Activity")
    assert res_pref.chosen_option == "hiking"


def test_empty_input():
    """Empty records return chosen_option=None with informative reason."""
    res = decide([], method="majority")
    assert res.chosen_option is None
    assert "Empty" in (res.reason or "")
    assert res.ranking == []
    assert res.scores == {}


# ---------------------------------------------------------------------------
# (6) No Positive Stances
# ---------------------------------------------------------------------------
def test_no_positive_stances():
    """When records contain only negative or neutral stances, chosen_option is None."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "negative", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "neutral", "value": {"name": "kandy"}},
    ]

    res_maj = decide(records, method="majority")
    assert res_maj.chosen_option is None
    assert "No positive preferences" in (res_maj.reason or "")

    res_pref = decide(records, method="preference_only")
    assert res_pref.chosen_option is None
    assert "No positive preferences" in (res_pref.reason or "")


# ---------------------------------------------------------------------------
# (7) Split vs Latest Majority Policy
# ---------------------------------------------------------------------------
def test_split_vs_latest_majority_policy():
    """Alice likes both Ella and Kandy; Bob likes Kandy.

    Under 'split': Alice splits 0.5 to Ella, 0.5 to Kandy. Bob gives 1.0 to Kandy.
    Under 'latest': Alice's latest positive (Kandy) gets 1.0.
    """
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
    ]

    # Split policy
    res_split = decide(records, method="majority", config={"majority_policy": "split"})
    assert res_split.scores["ella"] == 0.5
    assert res_split.scores["kandy"] == 1.5
    assert res_split.chosen_option == "kandy"

    # Latest policy
    res_latest = decide(records, method="majority", config={"majority_policy": "latest"})
    assert res_latest.scores["ella"] == 0.0
    assert res_latest.scores["kandy"] == 2.0
    assert res_latest.chosen_option == "kandy"


# ---------------------------------------------------------------------------
# (8) Negative Veto On and Off
# ---------------------------------------------------------------------------
def test_negative_veto_on_and_off():
    """Option with highest positive score is vetoed when negative_veto=True,

    unless every option is vetoed.
    """
    records = [
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "surfing"}},
        {"member": "Bob", "category": "Activity", "stance": "positive", "value": {"name": "surfing"}},
        {"member": "Charlie", "category": "Activity", "stance": "negative", "value": {"name": "surfing"}},
        {"member": "Charlie", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
    ]

    # Veto off: surfing score = 2 - 1 = 1; hiking score = 1. Surfing ties or wins depending on weights
    res_off = decide(records, method="preference_only", category="Activity", config={"negative_veto": False})
    # Tie between surfing and hiking (scores: 1.0, 1.0)
    assert res_off.is_tie is True

    # Veto on: surfing has a rejection from Charlie -> surfing is vetoed!
    res_on = decide(records, method="preference_only", category="Activity", config={"negative_veto": True})
    assert res_on.chosen_option == "hiking"
    assert res_on.is_tie is False

    # When all options are rejected: none are excluded
    all_rejected_records = [
        {"member": "Alice", "category": "Activity", "stance": "negative", "value": {"name": "hiking"}},
        {"member": "Bob", "category": "Activity", "stance": "positive", "value": {"name": "hiking"}},
        {"member": "Alice", "category": "Activity", "stance": "positive", "value": {"name": "surfing"}},
        {"member": "Bob", "category": "Activity", "stance": "negative", "value": {"name": "surfing"}},
    ]
    res_all_veto = decide(all_rejected_records, method="preference_only", category="Activity", config={"negative_veto": True})
    # Both options have a rejection, so neither is excluded
    assert res_all_veto.chosen_option in ("hiking", "surfing")


# ---------------------------------------------------------------------------
# (9) Synonym Normalization
# ---------------------------------------------------------------------------
def test_synonym_normalization():
    """Synonyms should map to canonical name and aggregate votes."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "nuwaraeliya"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "Nuwara Eliya"}},
    ]
    res = decide(records, method="majority", category="Destination")
    assert res.chosen_option == "nuwara eliya"
    assert res.scores["nuwara eliya"] == 2.0


# ---------------------------------------------------------------------------
# (10) Duplicate Records
# ---------------------------------------------------------------------------
def test_duplicate_records_by_same_member(caplog):
    """Member's latest record overwrites earlier ones with warning."""
    with caplog.at_level(logging.WARNING):
        records = [
            {"member": "Alice", "category": "Destination", "stance": "negative", "value": {"name": "ella"}},
            {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},  # Latest
            {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        ]
        res = decide(records, method="majority", category="Destination")

    assert res.chosen_option == "ella"
    assert res.scores["ella"] == 2.0
    assert any("repeated records" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# (11) Invalid Stance Validation Error
# ---------------------------------------------------------------------------
def test_invalid_stance_raises_error():
    """Invalid stance string must raise ValidationError."""
    with pytest.raises(ValidationError):
        decide(
            [{"member": "Alice", "category": "Destination", "stance": "dislike", "value": {"name": "ella"}}],
            method="majority",
        )


# ---------------------------------------------------------------------------
# (12) Deterministic Output Across Repeated Runs
# ---------------------------------------------------------------------------
def test_deterministic_repeatability():
    """Repeated calls produce identical DecisionResult objects."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},
    ]

    first_res = decide(records, method="majority").to_dict()
    for _ in range(10):
        next_res = decide(records, method="majority").to_dict()
        assert first_res == next_res
