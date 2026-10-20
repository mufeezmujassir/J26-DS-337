"""Pytest suite for  Emotion-Intensity Weighted Voting.

Verifies:
(1) alpha = 0 gives exactly the same scores, ranking and choice as preference-only on demo groups.
(2) use_emotion = false gives the same as preference-only.
(3) Records with emotion=None get weight 1.
(4) Weight is always between w_min and w_max, including intensity 1.0 and large alpha.
(5) Negative stance with negative emotion at intensity 0.9 gets higher weight than at 0.2.
(6) Positive stance with negative emotion (mismatch) gets weight 1.
(7) Hand-built case where preference-only picks X and weighted picks Y with verified hand-calculated scores.
(8) Monotonicity: increasing intensity never lowers the score of the supported option.
(9) intensity_mode 'none' gives a binary boost; continuous scales with intensity.
(10) Edge cases: ties, one member, empty input, duplicate records, invalid config, and deterministic repeatability.
(11) Proposal beach vs historical site example with emotional shifts.
(12) Emotion adapter attach_emotion tests (policy 'max' vs 'latest').
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest
from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.decision.baselines import decide, preference_only
from app.group_decision.decision.emotion_adapter import attach_emotion
from app.group_decision.decision.schemas import EmotionSignal, PreferenceRecord
from app.group_decision.decision.weighted import weighted_vote

DEMO_GROUPS_PATH = ROOT_DIR / "data" / "processed" / "decision_demo_groups.json"



# (1) alpha = 0 gives exactly the same scores, ranking and choice as preference-only

def test_alpha_zero_identical_to_preference_only():
    """alpha = 0 must match preference-only scores, ranking and choice across every demo group."""
    if not DEMO_GROUPS_PATH.exists():
        pytest.skip("Demo groups file not found")

    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        groups = json.load(f)

    for g in groups:
        category = g.get("category", "Destination")
        records = g.get("records", [])

        pref_res = decide(records, method="preference_only", category=category)
        wgt_res = decide(
            records,
            method="weighted",
            category=category,
            config={"weighted": {"alpha": 0.0, "w_min": 1.0, "w_max": 2.0}},
        )

        assert wgt_res.chosen_option == pref_res.chosen_option, f"Choice mismatch on {g['group_id']}"
        assert wgt_res.scores == pref_res.scores, f"Scores mismatch on {g['group_id']}"
        assert wgt_res.is_tie == pref_res.is_tie, f"Tie mismatch on {g['group_id']}"
        assert wgt_res.tied_options == pref_res.tied_options, f"Tied options mismatch on {g['group_id']}"
        assert wgt_res.outcome_changed_vs_preference_only is False



# (2) use_emotion = false gives the same as preference-only

def test_use_emotion_false_identical_to_preference_only():
    """When use_emotion is false, weighted voting must return exactly the preference-only result."""
    if not DEMO_GROUPS_PATH.exists():
        pytest.skip("Demo groups file not found")

    with open(DEMO_GROUPS_PATH, "r", encoding="utf-8") as f:
        groups = json.load(f)

    for g in groups:
        category = g.get("category", "Destination")
        records = g.get("records", [])

        pref_res = decide(records, method="preference_only", category=category)
        wgt_res = decide(
            records,
            method="weighted",
            category=category,
            config={"weighted": {"use_emotion": False}},
        )

        assert wgt_res.chosen_option == pref_res.chosen_option
        assert wgt_res.scores == pref_res.scores
        assert wgt_res.outcome_changed_vs_preference_only is False



# (3) Records with emotion=None get weight 1

def test_records_without_emotion_get_weight_one():
    """Records lacking an emotion signal must receive baseline weight 1.0."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}, "emotion": None},
        {"member": "Bob", "category": "Destination", "stance": "negative", "value": {"name": "ella"}},
    ]

    res = decide(records, method="weighted", category="Destination")

    assert len(res.contributions) == 2
    for item in res.contributions:
        assert item["weight"] == 1.0
        assert item["agreement"] == 0
        assert "baseline weight 1.0" in item["reason"]


# (4) Weight is always between w_min and w_max, including large alpha & intensity 1.0

def test_weight_bounded_by_w_min_and_w_max():
    """Weights must strictly clip within [w_min, w_max], even with extreme alpha."""
    records = [
        {
            "member": "Alice",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "ella"},
            "emotion": {"intensity": 1.0, "valence_sign": 1, "dominant_emotion": "joy"},
        }
    ]

    # Extreme alpha 100.0, bounds [1.0, 2.0] -> should clip to 2.0
    res1 = decide(
        records,
        method="weighted",
        category="Destination",
        config={"weighted": {"alpha": 100.0, "w_min": 1.0, "w_max": 2.0}},
    )
    assert res1.contributions[0]["weight"] == 2.0

    # Custom bounds [1.5, 2.5], alpha=0.0 -> raw is 1.0, clipped to w_min 1.5
    res2 = decide(
        records,
        method="weighted",
        category="Destination",
        config={"weighted": {"alpha": 0.0, "w_min": 1.5, "w_max": 2.5}},
    )
    assert res2.contributions[0]["weight"] == 1.5

    # Intermediate clipping: alpha=2.0, intensity=0.5 -> raw=2.0, w_max=1.8 -> clipped to 1.8
    res3 = decide(
        records,
        method="weighted",
        category="Destination",
        config={"weighted": {"alpha": 2.0, "w_min": 0.5, "w_max": 1.8}},
    )
    assert res3.contributions[0]["weight"] == 1.8



# (5) Negative stance with negative emotion: intensity 0.9 vs 0.2

def test_negative_stance_strong_opposition_counts_more():
    """Stronger negative emotion on a negative stance yields a higher opposition weight."""
    rec_strong = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {
            "member": "Bob",
            "category": "Destination",
            "stance": "negative",
            "value": {"name": "ella"},
            "emotion": {"intensity": 0.9, "valence_sign": -1, "dominant_emotion": "anger"},
        },
    ]

    rec_mild = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {
            "member": "Bob",
            "category": "Destination",
            "stance": "negative",
            "value": {"name": "ella"},
            "emotion": {"intensity": 0.2, "valence_sign": -1, "dominant_emotion": "annoyance"},
        },
    ]

    res_strong = decide(rec_strong, method="weighted", category="Destination")
    res_mild = decide(rec_mild, method="weighted", category="Destination")

    bob_strong_contrib = next(c for c in res_strong.contributions if c["member"] == "Bob")
    bob_mild_contrib = next(c for c in res_mild.contributions if c["member"] == "Bob")

    # Alpha 1.0 default:
    # Strong: 1 + 1.0 * 0.9 = 1.9 -> contribution = -1.9
    # Mild:   1 + 1.0 * 0.2 = 1.2 -> contribution = -1.2
    assert bob_strong_contrib["weight"] == 1.9
    assert bob_mild_contrib["weight"] == 1.2
    assert bob_strong_contrib["contribution"] == -1.9
    assert bob_mild_contrib["contribution"] == -1.2

    # Option score with strong opposition (1.0 - 1.9 = -0.9) < with mild opposition (1.0 - 1.2 = -0.2)
    assert res_strong.scores["ella"] < res_mild.scores["ella"]



# (6) Positive stance with negative emotion (mismatch) gets weight 1

def test_stance_valence_mismatch_gets_weight_one():
    """A positive stance paired with negative emotion (mismatch) gets agreement=0 and weight 1.0."""
    records = [
        {
            "member": "Alice",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "ella"},
            "emotion": {"intensity": 0.85, "valence_sign": -1, "dominant_emotion": "anger"},
        }
    ]

    res = decide(records, method="weighted", category="Destination")
    contrib = res.contributions[0]

    assert contrib["agreement"] == 0
    assert contrib["weight"] == 1.0
    assert contrib["contribution"] == 1.0
    assert "Mismatch: positive stance with negative emotion" in contrib["reason"]



# (7) Hand-built case where preference-only picks X, weighted picks Y

def test_hand_built_outcome_flip_with_exact_scores():
    """Hand-built case verifying exact scores calculated by hand.

    ========================================================================
    HAND CALCULATION & VERIFICATION BY HAND:
    ========================================================================
    Group of 3 members deciding between Destination 'ella' and 'kandy'.
    Candidate options: ['ella', 'kandy']

    Records:
    1. Alice: positive 'ella', emotion None
       - Stance weight: +1.0
       - Emotion: None -> agreement = 0
       - Weight: w = clip(1 + 1.5 * 0 * 0, 1.0, 3.0) = 1.0
       - Alice contribution to ella = 1.0 * (+1.0) = +1.0

    2. Bob: positive 'ella', emotion None
       - Stance weight: +1.0
       - Emotion: None -> agreement = 0
       - Weight: w = clip(1 + 1.5 * 0 * 0, 1.0, 3.0) = 1.0
       - Bob contribution to ella = 1.0 * (+1.0) = +1.0

    3. Charlie: positive 'kandy', joy intensity 0.90, valence_sign +1
       - Stance weight: +1.0
       - Emotion: joy, intensity=0.9, valence_sign=+1 -> agreement = 1
       - With config: alpha = 1.5, w_min = 1.0, w_max = 3.0
       - Raw weight: 1.0 + 1.5 * 0.90 * 1 = 1.0 + 1.35 = 2.35
       - Clipped weight: w = clip(2.35, 1.0, 3.0) = 2.35
       - Charlie contribution to kandy = 2.35 * (+1.0) = +2.35

    PREFERENCE-ONLY AGGREGATION:
    - score('ella')  = 1.0 (Alice) + 1.0 (Bob) = 2.0
    - score('kandy') = 1.0 (Charlie) = 1.0
    - Preference-Only Winner: 'ella' (2.0 > 1.0)

    WEIGHTED VOTING AGGREGATION:
    - score('ella')  = 1.0 (Alice) + 1.0 (Bob) = 2.0
    - score('kandy') = 2.35 (Charlie) = 2.35
    - Weighted Winner: 'kandy' (2.35 > 2.0)

    CONCLUSION:
    - Outcome flips from 'ella' (preference-only) to 'kandy' (weighted)!
    - outcome_changed_vs_preference_only must be True.
    ========================================================================
    """
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
        {
            "member": "Charlie",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "kandy"},
            "emotion": {"intensity": 0.90, "valence_sign": 1, "dominant_emotion": "joy"},
        },
    ]

    custom_cfg = {"weighted": {"alpha": 1.5, "w_min": 1.0, "w_max": 3.0}}

    # 1. Verify preference-only
    pref_res = decide(records, method="preference_only", category="Destination", config=custom_cfg)
    assert pref_res.scores["ella"] == 2.0
    assert pref_res.scores["kandy"] == 1.0
    assert pref_res.chosen_option == "ella"

    # 2. Verify weighted voting exact scores
    wgt_res = decide(records, method="weighted", category="Destination", config=custom_cfg)
    assert wgt_res.scores["ella"] == 2.0
    assert wgt_res.scores["kandy"] == 2.35
    assert wgt_res.chosen_option == "kandy"
    assert wgt_res.outcome_changed_vs_preference_only is True

    # 3. Verify contributions details
    c_map = {c["member"]: c for c in wgt_res.contributions}
    assert c_map["Alice"]["weight"] == 1.0
    assert c_map["Alice"]["contribution"] == 1.0
    assert c_map["Bob"]["weight"] == 1.0
    assert c_map["Bob"]["contribution"] == 1.0
    assert c_map["Charlie"]["weight"] == 2.35
    assert c_map["Charlie"]["contribution"] == 2.35



# (8) Monotonicity: increasing intensity never lowers the supported option's score

def test_monotonicity_increasing_intensity():
    """Increasing a supporter's emotion intensity must never reduce the option's score."""
    intensities = [0.0, 0.2, 0.5, 0.8, 1.0]
    previous_score = -float("inf")

    for intensity in intensities:
        records = [
            {
                "member": "Alice",
                "category": "Destination",
                "stance": "positive",
                "value": {"name": "ella"},
                "emotion": {"intensity": intensity, "valence_sign": 1, "dominant_emotion": "joy"},
            }
        ]
        res = decide(records, method="weighted", category="Destination")
        curr_score = res.scores["ella"]
        assert curr_score >= previous_score, f"Monotonicity violated at intensity {intensity}"
        previous_score = curr_score



# (9) intensity_mode 'none' gives a binary boost; continuous scales with intensity

def test_intensity_mode_none_vs_continuous():
    """intensity_mode='none' gives a constant binary boost; 'continuous' scales linearly."""
    # 1. intensity_mode = 'none'
    rec_low = [
        {
            "member": "Alice",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "ella"},
            "emotion": {"intensity": 0.1, "valence_sign": 1, "dominant_emotion": "joy"},
        }
    ]
    rec_high = [
        {
            "member": "Alice",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "ella"},
            "emotion": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"},
        }
    ]

    cfg_none = {"weighted": {"intensity_mode": "none", "alpha": 1.0}}
    res_none_low = decide(rec_low, method="weighted", category="Destination", config=cfg_none)
    res_none_high = decide(rec_high, method="weighted", category="Destination", config=cfg_none)

    # In 'none' mode, both get intensity_term=1.0 -> weight = 1 + 1.0*1.0 = 2.0
    assert res_none_low.contributions[0]["weight"] == 2.0
    assert res_none_high.contributions[0]["weight"] == 2.0

    # 2. intensity_mode = 'continuous'
    cfg_cont = {"weighted": {"intensity_mode": "continuous", "alpha": 1.0}}
    res_cont_low = decide(rec_low, method="weighted", category="Destination", config=cfg_cont)
    res_cont_high = decide(rec_high, method="weighted", category="Destination", config=cfg_cont)

    assert res_cont_low.contributions[0]["weight"] == 1.1
    assert res_cont_high.contributions[0]["weight"] == 1.9
    assert res_cont_high.contributions[0]["weight"] > res_cont_low.contributions[0]["weight"]



# (10) Edge cases: ties, one member, empty input, duplicate records, invalid config

def test_edge_cases_and_validation():
    """Verify tie breaking, single member, empty input, duplicate records, and invalid config."""
    # 10a. Tie case
    tie_records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "ella"}},
    ]
    tie_res = decide(tie_records, method="weighted", category="Destination")
    assert tie_res.is_tie is True
    assert set(tie_res.tied_options) == {"ella", "kandy"}
    # Alphabetical tie-break picks "ella"
    assert tie_res.chosen_option == "ella"

    # 10b. One member
    one_res = decide(
        [{"member": "Solo", "category": "Destination", "stance": "positive", "value": {"name": "sigiriya"}}],
        method="weighted",
        category="Destination",
    )
    assert one_res.chosen_option == "sigiriya"
    assert one_res.is_tie is False
    assert one_res.has_majority is True

    # 10c. Empty input
    empty_res = decide([], method="weighted", category="Destination")
    assert empty_res.chosen_option is None
    assert empty_res.scores == {}
    assert empty_res.ranking == []

    # 10d. Duplicate records for same member and option
    dup_records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}, "emotion": {"intensity": 0.2, "valence_sign": 1, "dominant_emotion": "joy"}},
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}, "emotion": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"}},
    ]
    # Max policy should use highest intensity 0.9
    dup_res = decide(dup_records, method="weighted", category="Destination", config={"weighted": {"aggregation_policy": "max"}})
    assert len(dup_res.contributions) == 1
    assert dup_res.contributions[0]["intensity"] == 0.9

    # 10e. Invalid config raising ValueError
    with pytest.raises(ValueError, match="alpha"):
        decide(tie_records, method="weighted", config={"weighted": {"alpha": -1.0}})

    with pytest.raises(ValueError, match="w_min"):
        decide(tie_records, method="weighted", config={"weighted": {"w_min": -0.5}})

    with pytest.raises(ValueError, match="w_max"):
        decide(tie_records, method="weighted", config={"weighted": {"w_min": 2.5, "w_max": 2.0}})

    with pytest.raises(ValueError, match="intensity_mode"):
        decide(tie_records, method="weighted", config={"weighted": {"intensity_mode": "invalid_mode"}})

    with pytest.raises(ValueError, match="aggregation_policy"):
        decide(tie_records, method="weighted", config={"weighted": {"aggregation_policy": "invalid_policy"}})

    with pytest.raises(ValidationError):
        # Invalid intensity > 1.0
        decide(
            [{
                "member": "Alice",
                "category": "Destination",
                "stance": "positive",
                "value": {"name": "ella"},
                "emotion": {"intensity": 1.5, "valence_sign": 1, "dominant_emotion": "joy"},
            }],
            method="weighted",
        )

    # 10f. Deterministic repeatability
    res_first = decide(tie_records, method="weighted").to_dict()
    for _ in range(10):
        res_next = decide(tie_records, method="weighted").to_dict()
        assert res_first == res_next


# (11) Proposal beach vs historical site example with emotional shifts

def test_proposal_beach_vs_historical_site_emotional_shift():
    """Proposal beach vs historical site: outcome shifts depending on who is emotional."""
    # Charlie is strongly emotional (opposes beach, loves historical site)
    records_charlie_emotional = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "beach"}},
        {
            "member": "Charlie",
            "category": "Destination",
            "stance": "negative",
            "value": {"name": "beach"},
            "emotion": {"intensity": 0.9, "valence_sign": -1, "dominant_emotion": "anger"},
        },
        {
            "member": "Charlie",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "historical site"},
            "emotion": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"},
        },
    ]

    res_charlie = decide(records_charlie_emotional, method="weighted", category="Destination")
    # beach score: +1.0 (Alice) + 1.0 (Bob) - 1.9 (Charlie) = +0.1
    # historical site: +1.9 (Charlie)
    assert res_charlie.scores["beach"] == 0.1
    assert res_charlie.scores["historical site"] == 1.9
    assert res_charlie.chosen_option == "historical site"

    # Alice and Bob are strongly emotional (love beach), Charlie has mild emotion
    records_alice_bob_emotional = [
        {
            "member": "Alice",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "beach"},
            "emotion": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"},
        },
        {
            "member": "Bob",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "beach"},
            "emotion": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "excitement"},
        },
        {
            "member": "Charlie",
            "category": "Destination",
            "stance": "negative",
            "value": {"name": "beach"},
            "emotion": {"intensity": 0.1, "valence_sign": -1, "dominant_emotion": "annoyance"},
        },
        {
            "member": "Charlie",
            "category": "Destination",
            "stance": "positive",
            "value": {"name": "historical site"},
            "emotion": {"intensity": 0.1, "valence_sign": 1, "dominant_emotion": "approval"},
        },
    ]

    res_alice_bob = decide(records_alice_bob_emotional, method="weighted", category="Destination")
    # beach score: +1.9 (Alice) + 1.9 (Bob) - 1.1 (Charlie) = +2.7
    # historical site: +1.1 (Charlie)
    assert res_alice_bob.scores["beach"] == 2.7
    assert res_alice_bob.scores["historical site"] == 1.1
    assert res_alice_bob.chosen_option == "beach"



# (12) Emotion Adapter attach_emotion

def test_emotion_adapter_attach_emotion():
    """attach_emotion associates signals via message_id, respecting 'max' and 'latest' policies."""
    records = [
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}, "message_id": "msg_1"},
        {"member": "Alice", "category": "Destination", "stance": "positive", "value": {"name": "ella"}, "message_id": "msg_2"},
        {"member": "Bob", "category": "Destination", "stance": "positive", "value": {"name": "kandy"}, "message_id": "msg_3"},
        {"member": "Charlie", "category": "Destination", "stance": "positive", "value": {"name": "galle"}},  # No message_id
    ]

    signals = {
        "msg_1": {"intensity": 0.4, "valence_sign": 1, "dominant_emotion": "optimism"},
        "msg_2": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"},
        "msg_3": {"intensity": 0.7, "valence_sign": 1, "dominant_emotion": "excitement"},
    }

    # Policy 'max': Alice gets msg_2 (0.9)
    attached_max = attach_emotion(records, signals, policy="max")
    assert attached_max[0].emotion.intensity == 0.9
    assert attached_max[0].emotion.dominant_emotion == "joy"
    assert attached_max[2].emotion.intensity == 0.7
    assert attached_max[3].emotion is None

    # Reverse signals intensity order to test 'latest' vs 'max'
    signals_rev = {
        "msg_1": {"intensity": 0.9, "valence_sign": 1, "dominant_emotion": "joy"},
        "msg_2": {"intensity": 0.3, "valence_sign": 1, "dominant_emotion": "optimism"},
    }
    # Policy 'latest': Alice gets msg_2 (0.3)
    attached_latest = attach_emotion(records, signals_rev, policy="latest")
    assert attached_latest[0].emotion.intensity == 0.3

    # Invalid policy raises ValueError
    with pytest.raises(ValueError, match="Invalid aggregation policy"):
        attach_emotion(records, signals, policy="invalid")
