"""Pytest suite for Emotion Expression Intensity Estimator (WANDARAYA Component 3 Step 8).

Verifies multi-cue intensity scoring, boundary limits [0.0, 1.0], lexical boosts,
negation handling, punctuation weighting, neutral capping, and deterministic behavior
without requiring GPU or model weights.
"""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

# Ensure root directory is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.group_decision.intensity.estimator import (
    DEFAULT_GOEMOTIONS_LABELS,
    estimate_intensity,
)


@pytest.fixture
def fake_positive_probs() -> dict[str, float]:
    """Mock probabilities where 'love' is high and dominant."""
    probs = {label: 0.01 for label in DEFAULT_GOEMOTIONS_LABELS}
    probs["love"] = 0.92
    probs["joy"] = 0.40
    probs["neutral"] = 0.05
    return probs


@pytest.fixture
def fake_neutral_probs() -> dict[str, float]:
    """Mock probabilities where 'neutral' is the top label."""
    probs = {label: 0.02 for label in DEFAULT_GOEMOTIONS_LABELS}
    probs["neutral"] = 0.85
    return probs


@pytest.fixture
def fake_subthreshold_probs() -> dict[str, float]:
    """Mock probabilities where all non-neutral emotions are below 0.5 threshold."""
    probs = {label: 0.20 for label in DEFAULT_GOEMOTIONS_LABELS}
    probs["neutral"] = 0.30
    return probs


@pytest.fixture
def default_thresholds() -> dict[str, float]:
    """Standard 0.5 thresholds for all 28 classes."""
    return {label: 0.5 for label in DEFAULT_GOEMOTIONS_LABELS}


def test_intensity_output_bounds_empty_and_long_text(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that intensity is always strictly between 0.0 and 1.0, including empty and long texts."""
    # 1. Empty string
    res_empty = estimate_intensity("", fake_positive_probs, default_thresholds)
    assert 0.0 <= res_empty["intensity"] <= 1.0
    assert "components" in res_empty
    assert 0.0 <= res_empty["components"]["model"] <= 1.0
    assert res_empty["components"]["lexical"] == 0.0
    assert res_empty["components"]["punctuation"] == 0.0

    # 2. Very long text (exceeding typical message length)
    long_text = "I love this wonderful place so much! " * 200
    res_long = estimate_intensity(long_text, fake_positive_probs, default_thresholds)
    assert 0.0 <= res_long["intensity"] <= 1.0
    for comp_name, comp_val in res_long["components"].items():
        assert 0.0 <= comp_val <= 1.0, f"Component {comp_name} out of bounds: {comp_val}"


def test_lexical_and_punctuation_boost_ordering(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that 'I really love it!!!' > 'I love it' > 'it is okay I guess'."""
    text_high = "I really love it!!!"
    text_mid = "I love it"
    text_low = "it is okay I guess"

    low_probs = {label: 0.02 for label in DEFAULT_GOEMOTIONS_LABELS}
    low_probs["approval"] = 0.51
    low_probs["neutral"] = 0.20

    res_high = estimate_intensity(text_high, fake_positive_probs, default_thresholds)
    res_mid = estimate_intensity(text_mid, fake_positive_probs, default_thresholds)
    res_low = estimate_intensity(text_low, low_probs, default_thresholds)

    assert res_high["intensity"] > res_mid["intensity"], (
        f"Expected '{text_high}' ({res_high['intensity']}) > '{text_mid}' ({res_mid['intensity']})"
    )
    assert res_mid["intensity"] > res_low["intensity"], (
        f"Expected '{text_mid}' ({res_mid['intensity']}) > '{text_low}' ({res_low['intensity']})"
    )


def test_exclamation_mark_scaling(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that '!!!' scores higher than '!' in punctuation and final intensity."""
    res_three_excl = estimate_intensity("This is great!!!", fake_positive_probs, default_thresholds)
    res_one_excl = estimate_intensity("This is great!", fake_positive_probs, default_thresholds)

    assert res_three_excl["components"]["punctuation"] > res_one_excl["components"]["punctuation"]
    assert res_three_excl["intensity"] > res_one_excl["intensity"]


def test_negation_cancels_or_reduces_intensity(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that negation ('I don't really love it') scores lower than ('I really love it')."""
    res_affirmative = estimate_intensity("I really love it", fake_positive_probs, default_thresholds)
    res_negated = estimate_intensity("I don't really love it", fake_positive_probs, default_thresholds)

    assert res_negated["components"]["lexical"] < res_affirmative["components"]["lexical"]
    assert res_negated["intensity"] < res_affirmative["intensity"], (
        f"Negated '{res_negated['intensity']}' should be less than affirmative '{res_affirmative['intensity']}'"
    )


def test_neutral_dominant_caps_intensity_at_point_one(
    fake_neutral_probs: dict[str, float],
    fake_subthreshold_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that when neutral is dominant or non-neutral scores are subthreshold, intensity <= 0.1."""
    # 1. Neutral top label with loud punctuation
    res_neutral = estimate_intensity("It is okay I guess!!!", fake_neutral_probs, default_thresholds)
    assert res_neutral["dominant_emotion"] == "neutral"
    assert res_neutral["valence"] == "neutral"
    assert res_neutral["valence_sign"] == 0
    assert res_neutral["intensity"] <= 0.1001, f"Expected <= 0.1, got {res_neutral['intensity']}"

    # 2. All non-neutral scores below threshold
    res_subthreshold = estimate_intensity("Everything is fine.", fake_subthreshold_probs, default_thresholds)
    assert res_subthreshold["dominant_emotion"] == "neutral"
    assert res_subthreshold["intensity"] <= 0.1001, f"Expected <= 0.1, got {res_subthreshold['intensity']}"


def test_invalid_weights_raise_value_error(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that component weights not summing to 1.0 raise a clear ValueError."""
    invalid_config = {
        "weights": {"model": 0.5, "lexical": 0.5, "punctuation": 0.5},  # sums to 1.5
    }

    with pytest.raises(ValueError, match="must sum to 1.0"):
        estimate_intensity(
            "I love it",
            fake_positive_probs,
            default_thresholds,
            config_override=invalid_config,
        )


def test_determinism_and_components_structure(
    fake_positive_probs: dict[str, float],
    default_thresholds: dict[str, float],
) -> None:
    """Test that outputs are strictly deterministic and include required component keys."""
    text = "WE ABSOLUTELY ADORE THIS HOTEL!!!"

    run1 = estimate_intensity(text, fake_positive_probs, default_thresholds)
    run2 = estimate_intensity(text, fake_positive_probs, default_thresholds)

    assert run1 == run2, "Output must be completely deterministic"

    # Verify dictionary structure
    assert "intensity" in run1
    assert "dominant_emotion" in run1
    assert "valence" in run1
    assert "valence_sign" in run1
    assert "components" in run1

    comp = run1["components"]
    assert "model" in comp
    assert "lexical" in comp
    assert "punctuation" in comp
    assert comp["punctuation"] > 0.5  # ALL-CAPS + exclamation marks
    assert comp["lexical"] > 0.4      # absolutely + adore


def test_valence_and_valence_signs(default_thresholds: dict[str, float]) -> None:
    """Test positive (+1), negative (-1), ambiguous (0), and neutral (0) valence signs."""
    # Positive: Joy
    joy_probs = {c: 0.01 for c in DEFAULT_GOEMOTIONS_LABELS}
    joy_probs["joy"] = 0.90
    res_joy = estimate_intensity("So happy!", joy_probs, default_thresholds)
    assert res_joy["valence"] == "positive"
    assert res_joy["valence_sign"] == 1

    # Negative: Anger
    anger_probs = {c: 0.01 for c in DEFAULT_GOEMOTIONS_LABELS}
    anger_probs["anger"] = 0.90
    res_anger = estimate_intensity("This is awful!", anger_probs, default_thresholds)
    assert res_anger["valence"] == "negative"
    assert res_anger["valence_sign"] == -1

    # Ambiguous: Surprise
    surp_probs = {c: 0.01 for c in DEFAULT_GOEMOTIONS_LABELS}
    surp_probs["surprise"] = 0.90
    res_surp = estimate_intensity("What?!", surp_probs, default_thresholds)
    assert res_surp["valence"] == "ambiguous"
    assert res_surp["valence_sign"] == 0

    # Neutral: Neutral
    neut_probs = {c: 0.01 for c in DEFAULT_GOEMOTIONS_LABELS}
    neut_probs["neutral"] = 0.90
    res_neut = estimate_intensity("It is a train.", neut_probs, default_thresholds)
    assert res_neut["valence"] == "neutral"
    assert res_neut["valence_sign"] == 0
