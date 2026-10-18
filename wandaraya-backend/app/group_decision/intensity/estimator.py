"""Expression intensity estimation module for WANDARAYA Component 3.

This module estimates the 'expression intensity' of text messages—measuring how
strongly an emotion is EXPRESSED in the surface text (linguistic force, rhetorical
emphasis, and punctuation).

Important note on terminology:
This is an expression intensity estimator. It measures the strength of verbal/written
expression in the text itself, NOT a measurement of a person's true internal psychological state.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
import yaml

# Standard GoEmotions 28 labels
DEFAULT_GOEMOTIONS_LABELS: list[str] = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral"
]

DEFAULT_VALENCE_MAP: dict[str, list[str]] = {
    "positive": [
        "admiration", "amusement", "approval", "caring", "desire",
        "excitement", "gratitude", "joy", "love", "optimism", "pride", "relief"
    ],
    "negative": [
        "anger", "annoyance", "disappointment", "disapproval", "disgust",
        "embarrassment", "fear", "grief", "nervousness", "remorse", "sadness"
    ],
    "ambiguous": [
        "confusion", "curiosity", "realization", "surprise"
    ],
    "neutral": [
        "neutral"
    ],
}

DEFAULT_NEGATORS: set[str] = {
    "not", "don't", "dont", "never", "no", "cannot", "can't", "cant",
    "won't", "wont", "wouldn't", "wouldnt", "isn't", "isnt", "aren't",
    "arent", "wasn't", "wasnt", "weren't", "werent", "hardly", "scarcely",
    "neither", "nor", "nothing", "nowhere"
}

_CONFIG_CACHE: dict[str, Any] | None = None
_LEXICON_CACHE: dict[str, list[str]] | None = None


def load_intensity_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load intensity configuration from configs/config.yaml with robust fallbacks."""
    global _CONFIG_CACHE
    path = Path(config_path or "configs/config.yaml")

    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                root_cfg = yaml.safe_load(f) or {}
                if "intensity_estimator" in root_cfg:
                    _CONFIG_CACHE = root_cfg["intensity_estimator"]
                    return _CONFIG_CACHE
        except Exception:
            pass

    # Default fallback config
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = {
            "weights": {"model": 0.5, "lexical": 0.3, "punctuation": 0.2},
            "lexicon_path": "configs/intensity_lexicon.yaml",
            "neutral_max_intensity": 0.1,
            "valence_map": DEFAULT_VALENCE_MAP,
            "caps": {
                "exclamation_cap": 3,
                "exclamation_weight": 0.40,
                "caps_weight": 0.30,
                "elongation_weight": 0.20,
                "question_weight": 0.10,
            },
            "lexical_scoring": {
                "intensifier_boost": 0.25,
                "strong_word_boost": 0.35,
                "downtoner_penalty": 0.20,
                "negation_window": 3,
            },
        }
    return _CONFIG_CACHE


def load_intensity_lexicon(lexicon_path: str | Path | None = None) -> dict[str, list[str]]:
    """Load intensifiers, downtoners, and strong emotion words from YAML."""
    global _LEXICON_CACHE
    path = Path(lexicon_path or "configs/intensity_lexicon.yaml")

    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                lex = yaml.safe_load(f)
                if isinstance(lex, dict):
                    _LEXICON_CACHE = {
                        "intensifiers": [w.lower() for w in lex.get("intensifiers", [])],
                        "downtoners": [w.lower() for w in lex.get("downtoners", [])],
                        "strong_emotion_words": [w.lower() for w in lex.get("strong_emotion_words", [])],
                    }
                    return _LEXICON_CACHE
        except Exception:
            pass

    if _LEXICON_CACHE is None:
        _LEXICON_CACHE = {
            "intensifiers": ["really", "absolutely", "so", "totally", "extremely", "very", "incredibly", "super"],
            "downtoners": ["kind of", "sort of", "a bit", "a little", "slightly", "maybe", "somewhat"],
            "strong_emotion_words": ["love", "hate", "adore", "can't stand", "amazing", "terrible", "awesome", "awful"],
        }
    return _LEXICON_CACHE


def _tokenize_words(text: str) -> list[str]:
    """Tokenize text into lowercase words while preserving apostrophes in contractions."""
    return re.findall(r"\b[a-zA-Z']+\b", text.lower())


def compute_model_component(
    probs: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> tuple[float, str, bool]:
    """Compute Component 1: Rescaled dominant emotion probability score.

    Rescales relative to the class threshold: (p - thr) / (1 - thr), clipped to 0-1.
    If neutral is top, or all non-neutral scores are below threshold,
    dominant_emotion is 'neutral'.

    Returns:
        (model_score, dominant_emotion, is_neutral_dominant)
    """
    if not probs:
        return 0.0, "neutral", True

    if thresholds is None:
        thresholds = {k: 0.5 for k in probs.keys()}

    top_overall_label = max(probs, key=probs.get)
    non_neutral_keys = [k for k in probs.keys() if k != "neutral"]

    # Check if all non-neutral labels are strictly below their decision threshold
    all_below_thresh = True
    if non_neutral_keys:
        for k in non_neutral_keys:
            thr = float(thresholds.get(k, 0.5))
            if float(probs[k]) >= thr:
                all_below_thresh = False
                break

    if top_overall_label == "neutral" or all_below_thresh or not non_neutral_keys:
        return 0.0, "neutral", True

    dominant_emotion = max(non_neutral_keys, key=probs.get)
    p = float(probs[dominant_emotion])
    thr = float(thresholds.get(dominant_emotion, 0.5))

    if thr >= 1.0:
        rescaled = 0.0
    else:
        rescaled = (p - thr) / (1.0 - thr)

    model_score = max(0.0, min(1.0, float(rescaled)))
    return model_score, dominant_emotion, False


def compute_lexical_component(
    text: str,
    lexicon: dict[str, list[str]],
    scoring_params: dict[str, Any],
) -> float:
    """Compute Component 2: Lexical intensity score with 3-token negation handling."""
    if not text or not text.strip():
        return 0.0

    intensifiers = set(lexicon.get("intensifiers", []))
    downtoners = lexicon.get("downtoners", [])
    strong_words = set(lexicon.get("strong_emotion_words", []))

    boost_intensifier = float(scoring_params.get("intensifier_boost", 0.25))
    boost_strong = float(scoring_params.get("strong_word_boost", 0.35))
    pen_downtoner = float(scoring_params.get("downtoner_penalty", 0.20))
    neg_window = int(scoring_params.get("negation_window", 3))

    lower_text = text.lower()
    tokens = _tokenize_words(lower_text)
    num_tokens = len(tokens)

    # 1. Check multi-token and single-token downtoners
    downtoner_count = 0
    matched_downtoner_spans = []

    for dt in downtoners:
        # Check phrase match in lower_text
        pattern = r"\b" + re.escape(dt) + r"\b"
        for match in re.finditer(pattern, lower_text):
            downtoner_count += 1
            matched_downtoner_spans.append((match.start(), match.end()))

    # 2. Token-by-token evaluation with negation window
    total_boost = 0.0

    for idx, token in enumerate(tokens):
        # Look behind up to neg_window tokens for a negator
        start_lookback = max(0, idx - neg_window)
        preceding_tokens = tokens[start_lookback:idx]
        is_negated = any(neg in DEFAULT_NEGATORS for neg in preceding_tokens)

        # Check intensifiers
        if token in intensifiers:
            if not is_negated:
                total_boost += boost_intensifier

        # Check strong emotion words
        if token in strong_words:
            if not is_negated:
                total_boost += boost_strong

    # Check multi-word strong phrases (e.g. "can't stand", "cannot stand")
    for phrase in ["can't stand", "cannot stand", "cant stand"]:
        if phrase in lower_text:
            total_boost += boost_strong

    raw_lexical = total_boost - (downtoner_count * pen_downtoner)
    return max(0.0, min(1.0, float(raw_lexical)))


def compute_punctuation_component(
    text: str,
    dominant_emotion: str,
    caps_cfg: dict[str, Any],
) -> float:
    """Compute Component 3: Punctuation and stylistic expression cues."""
    if not text or not text.strip():
        return 0.0

    excl_cap = int(caps_cfg.get("exclamation_cap", 3))
    w_excl = float(caps_cfg.get("exclamation_weight", 0.40))
    w_caps = float(caps_cfg.get("caps_weight", 0.30))
    w_elong = float(caps_cfg.get("elongation_weight", 0.20))
    w_quest = float(caps_cfg.get("question_weight", 0.10))

    # 1. Number of '!' (capped at excl_cap)
    excl_count = text.count("!")
    excl_subscore = min(excl_count, excl_cap) / float(excl_cap) if excl_cap > 0 else 0.0

    # 2. ALL-CAPS word ratio (ignore words of 1-2 letters and "I")
    raw_words = re.findall(r"\b[a-zA-Z]+\b", text)
    eligible_words = [w for w in raw_words if len(w) > 2 and w != "I"]
    if eligible_words:
        caps_words = [w for w in eligible_words if w.isupper()]
        caps_ratio = len(caps_words) / float(len(eligible_words))
    else:
        caps_ratio = 0.0
    caps_subscore = min(1.0, caps_ratio)

    # 3. Letter elongation (3+ repeated letters: e.g. 'sooo', 'goood')
    elongation_matches = re.findall(r"([a-zA-Z])\1{2,}", text)
    elong_subscore = min(len(elongation_matches), 2) / 2.0

    # 4. Question mark contribution (ONLY for confusion or curiosity)
    if dominant_emotion in ("confusion", "curiosity"):
        quest_count = text.count("?")
        quest_subscore = min(quest_count, 2) / 2.0
    else:
        quest_subscore = 0.0

    punct_score = (
        (w_excl * excl_subscore)
        + (w_caps * caps_subscore)
        + (w_elong * elong_subscore)
        + (w_quest * quest_subscore)
    )

    return max(0.0, min(1.0, float(punct_score)))


def determine_valence(
    dominant_emotion: str,
    valence_map: dict[str, list[str]],
) -> tuple[str, int]:
    """Map dominant emotion to valence category and valence sign (+1, -1, or 0)."""
    if dominant_emotion in valence_map.get("positive", []):
        return "positive", 1
    if dominant_emotion in valence_map.get("negative", []):
        return "negative", -1
    if dominant_emotion in valence_map.get("ambiguous", []):
        return "ambiguous", 0
    return "neutral", 0


def estimate_intensity(
    text: str,
    probs: dict[str, float],
    thresholds: dict[str, float] | None = None,
    config_path: str | Path | None = None,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate expression intensity of a message from predicted probabilities and text.

    Measures how strongly an emotion is EXPRESSED in the surface text.
    Does NOT load any neural network model.

    Args:
        text: Input message string.
        probs: Dict mapping emotion names to model probabilities (28 GoEmotions classes).
        thresholds: Optional dict mapping emotion names to decision thresholds (default: 0.5).
        config_path: Optional path to YAML config file.
        config_override: Optional dict to override intensity estimator settings.

    Returns:
        dict: {
            "intensity": float 0-1,
            "dominant_emotion": str,
            "valence": "positive"|"negative"|"neutral"|"ambiguous",
            "valence_sign": +1|-1|0,
            "components": {
                "model": float,
                "lexical": float,
                "punctuation": float
            }
        }
    """
    cfg = config_override or load_intensity_config(config_path)

    weights = cfg.get("weights", {"model": 0.5, "lexical": 0.3, "punctuation": 0.2})
    w_model = float(weights.get("model", 0.5))
    w_lex = float(weights.get("lexical", 0.3))
    w_punct = float(weights.get("punctuation", 0.2))

    # Weight validation: must strictly sum to 1.0
    w_sum = round(w_model + w_lex + w_punct, 6)
    if abs(w_sum - 1.0) > 1e-4:
        raise ValueError(
            f"Intensity component weights must sum to 1.0, got {w_sum} "
            f"(model={w_model}, lexical={w_lex}, punctuation={w_punct})"
        )

    lexicon_path = cfg.get("lexicon_path", "configs/intensity_lexicon.yaml")
    lexicon = load_intensity_lexicon(lexicon_path)
    caps_cfg = cfg.get("caps", {})
    scoring_params = cfg.get("lexical_scoring", {})
    valence_map = cfg.get("valence_map", DEFAULT_VALENCE_MAP)
    neutral_max = float(cfg.get("neutral_max_intensity", 0.1))

    # 1. Component 1: Model score
    model_score, dominant_emotion, is_neutral = compute_model_component(probs, thresholds)

    # 2. Component 2: Lexical score
    lexical_score = compute_lexical_component(text, lexicon, scoring_params)

    # 3. Component 3: Punctuation/style score
    punct_score = compute_punctuation_component(text, dominant_emotion, caps_cfg)

    # 4. Weighted combination
    raw_intensity = (w_model * model_score) + (w_lex * lexical_score) + (w_punct * punct_score)
    final_intensity = max(0.0, min(1.0, float(raw_intensity)))

    # If neutral is dominant or all scores below threshold, intensity must be at most 0.1
    if is_neutral or dominant_emotion == "neutral":
        final_intensity = min(final_intensity, neutral_max)

    # 5. Determine valence and valence_sign
    valence, valence_sign = determine_valence(dominant_emotion, valence_map)

    return {
        "intensity": round(final_intensity, 4),
        "dominant_emotion": dominant_emotion,
        "valence": valence,
        "valence_sign": valence_sign,
        "components": {
            "model": round(model_score, 4),
            "lexical": round(lexical_score, 4),
            "punctuation": round(punct_score, 4),
        },
    }
