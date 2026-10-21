"""Emotion-Intensity Weighted Voting (Step 10b).

Extends baseline decision mechanisms with emotion expression intensity weighting.
Deterministic, modular, and configurable via configs/config.yaml.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import yaml

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.baselines import (
    METHODS,
    _deduplicate_records,
    _resolve_tie,
    load_decision_config,
    preference_only,
    set_seed,
)
from app.group_decision.decision.emotion_adapter import attach_emotion
from app.group_decision.decision.schemas import DecisionResult, EmotionSignal, PreferenceRecord

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "config.yaml"


def validate_weighted_config(cfg: dict[str, Any]) -> None:
    """Validate weighted voting configuration parameters.

    Raises ValueError if thresholds or options violate constraints.
    """
    alpha = cfg.get("alpha", 1.0)
    w_min = cfg.get("w_min", 1.0)
    w_max = cfg.get("w_max", 2.0)
    intensity_mode = cfg.get("intensity_mode", "continuous")
    aggregation_policy = cfg.get("aggregation_policy", "max")

    if not isinstance(alpha, (int, float)) or alpha < 0:
        raise ValueError(f"Invalid alpha '{alpha}': alpha must be a non-negative number.")

    if not isinstance(w_min, (int, float)) or w_min < 0:
        raise ValueError(f"Invalid w_min '{w_min}': w_min must be >= 0.")

    if not isinstance(w_max, (int, float)) or w_max < w_min:
        raise ValueError(f"Invalid w_max '{w_max}': w_max must be >= w_min ({w_min}).")

    if intensity_mode not in ("continuous", "none"):
        raise ValueError(
            f"Invalid intensity_mode '{intensity_mode}'. Allowed: 'continuous', 'none'."
        )

    if aggregation_policy not in ("max", "latest"):
        raise ValueError(
            f"Invalid aggregation_policy '{aggregation_policy}'. Allowed: 'max', 'latest'."
        )


def load_weighted_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate decision configuration with weighted voting parameters."""
    base_cfg = load_decision_config(config_path)

    # Defaults for weighted voting
    weighted_defaults: dict[str, Any] = {
        "alpha": 1.0,
        "w_min": 1.0,
        "w_max": 2.0,
        "intensity_mode": "continuous",
        "use_emotion": True,
        "aggregation_policy": "max",
    }

    raw_weighted = base_cfg.get("weighted", {})
    for k, v in weighted_defaults.items():
        if k not in raw_weighted:
            raw_weighted[k] = v

    if overrides:
        # Check if overrides are top-level or under 'weighted'
        if "weighted" in overrides and isinstance(overrides["weighted"], dict):
            raw_weighted.update(overrides["weighted"])
        for k in weighted_defaults.keys():
            if k in overrides:
                raw_weighted[k] = overrides[k]
        # Copy any other overrides
        for k, v in overrides.items():
            if k != "weighted" and k not in weighted_defaults:
                base_cfg[k] = v

    validate_weighted_config(raw_weighted)
    base_cfg["weighted"] = raw_weighted
    return base_cfg


def weighted_vote(
    records: list[Any],
    category: str = "Destination",
    candidate_options: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> DecisionResult:
    """Method 3: Emotion-intensity weighted voting.

    Weight per record:
        agreement = 1 if (stance is positive and valence_sign == +1) or
                         (stance is negative and valence_sign == -1)
                    else 0.
        intensity_term = emotion.intensity if intensity_mode == "continuous",
                         or 1.0 if intensity_mode == "none" and dominant_emotion != "neutral".
        w = clip(1 + alpha * intensity_term * agreement, w_min, w_max)

    Option score = sum over members of w * stance_weight[stance].
    When use_emotion is False, returns exactly the preference-only result.

    Args:
        records: List of preference records (dicts or PreferenceRecord instances).
        category: Category to decide on ('Destination' or 'Activity').
        candidate_options: Optional list of candidate option names.
        config: Optional configuration overrides.

    Returns:
        DecisionResult instance with contributions breakdown and outcome_changed flag.
    """
    set_seed(42)

    # Load and validate configuration
    cfg = load_weighted_config(overrides=config)
    w_cfg = cfg.get("weighted", {})
    validate_weighted_config(w_cfg)

    alpha = float(w_cfg.get("alpha", 1.0))
    w_min = float(w_cfg.get("w_min", 1.0))
    w_max = float(w_cfg.get("w_max", 2.0))
    intensity_mode = str(w_cfg.get("intensity_mode", "continuous"))
    use_emotion = bool(w_cfg.get("use_emotion", True))
    aggregation_policy = str(w_cfg.get("aggregation_policy", "max"))

    tie_break = cfg.get("tie_break", "alphabetical")
    stance_weights = cfg.get("stance_weights", {"positive": 1.0, "neutral": 0.0, "negative": -1.0})

    # Attach message signals if provided in config
    message_signals = cfg.get("message_signals")
    if message_signals and isinstance(message_signals, dict):
        records = attach_emotion(records, message_signals, policy=aggregation_policy)

    # Baseline preference-only result for comparison
    pref_res = preference_only(
        records=records,
        category=category,
        candidate_options=candidate_options,
        config=cfg,
    )

    # Deduplicate records: keeps latest record per (member, category, canon_name)
    active_records, mention_order = _deduplicate_records(records, category)

    # Candidate options determination
    if candidate_options is not None:
        candidates = [normalize_name(opt, category=category) for opt in candidate_options]
    else:
        candidates = list(mention_order)

    candidates = sorted(list(dict.fromkeys(candidates)))

    # Edge case 1: Empty input or no candidates
    if not records or not candidates:
        return DecisionResult(
            category=category,
            chosen_option=None,
            ranking=[],
            scores={c: 0.0 for c in candidates},
            is_tie=False,
            tied_options=[],
            has_majority=False,
            method="weighted",
            config=cfg,
            reason="Empty records input or no candidates found",
            contributions=[],
            outcome_changed_vs_preference_only=False,
        )

    # Edge case 2: No positive preferences in category
    has_any_positive = any(r.stance == "positive" for r in active_records)
    if not has_any_positive:
        return DecisionResult(
            category=category,
            chosen_option=None,
            ranking=[{"option": c, "score": 0.0} for c in candidates],
            scores={c: 0.0 for c in candidates},
            is_tie=False,
            tied_options=[],
            has_majority=False,
            method="weighted",
            config=cfg,
            reason="No positive preferences in category",
            contributions=[],
            outcome_changed_vs_preference_only=False,
        )

    # Multi-record emotion resolution under aggregation_policy
    # If a member had multiple records for the same option in raw records, ensure
    # the resolved emotion follows aggregation_policy (e.g. max intensity).
    if aggregation_policy == "max":
        member_opt_emotions: dict[tuple[str, str, str], list[EmotionSignal]] = {}
        for raw in records:
            r_obj = raw if isinstance(raw, PreferenceRecord) else PreferenceRecord.model_validate(raw)
            if r_obj.category == category and r_obj.emotion is not None:
                val = r_obj.value
                opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
                if opt_raw:
                    c_opt = normalize_name(opt_raw, category=category)
                    k = (r_obj.member, r_obj.category, c_opt)
                    if k not in member_opt_emotions:
                        member_opt_emotions[k] = []
                    member_opt_emotions[k].append(r_obj.emotion)

        for rec in active_records:
            val = rec.value
            opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
            if opt_raw:
                c_opt = normalize_name(opt_raw, category=category)
                k = (rec.member, rec.category, c_opt)
                if k in member_opt_emotions and member_opt_emotions[k]:
                    best_sig = max(member_opt_emotions[k], key=lambda s: s.intensity)
                    rec.emotion = best_sig

    # Compute weights, explainability contributions, and scores
    contributions: list[dict[str, Any]] = []
    option_scores: dict[str, float] = {c: 0.0 for c in candidates}
    member_stances: dict[str, dict[str, str]] = {}

    for rec in active_records:
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if not opt_raw:
            continue
        c_opt = normalize_name(opt_raw, category=category)
        if c_opt not in candidates:
            continue

        if rec.member not in member_stances:
            member_stances[rec.member] = {}
        member_stances[rec.member][c_opt] = rec.stance

        # Validate emotion intensity if present
        if rec.emotion is not None:
            if not isinstance(rec.emotion.intensity, (int, float)) or not (0.0 <= rec.emotion.intensity <= 1.0):
                raise ValueError(
                    f"Invalid emotion intensity {rec.emotion.intensity}: intensity must be in [0, 1]."
                )

        # Weight calculation
        if not use_emotion:
            agreement = 0
            intensity_val = rec.emotion.intensity if rec.emotion else None
            w = 1.0
            reason = "Emotion disabled (use_emotion=False): baseline weight 1.0"
        elif rec.emotion is None:
            agreement = 0
            intensity_val = None
            w = max(w_min, min(w_max, 1.0))
            reason = "Missing emotion signal: baseline weight 1.0"
        else:
            intensity_val = float(rec.emotion.intensity)
            dom_emotion = rec.emotion.dominant_emotion.lower()
            val_sign = int(rec.emotion.valence_sign)

            # Agreement: positive stance with +1 valence, or negative stance with -1 valence
            is_pos_match = (rec.stance == "positive" and val_sign == 1)
            is_neg_match = (rec.stance == "negative" and val_sign == -1)
            agreement = 1 if (is_pos_match or is_neg_match) else 0

            # Intensity term
            if intensity_mode == "continuous":
                intensity_term = intensity_val
            elif intensity_mode == "none":
                intensity_term = 1.0 if dom_emotion != "neutral" else 0.0
            else:
                raise ValueError(f"Invalid intensity_mode: {intensity_mode}")

            # Formula: w = clip(1 + alpha * intensity_term * agreement, w_min, w_max)
            raw_w = 1.0 + alpha * intensity_term * agreement
            w = max(w_min, min(w_max, raw_w))

            # Explainability reason
            if agreement == 1 and rec.stance == "positive":
                reason = (
                    f"Positive stance aligned with positive emotion ({dom_emotion}, intensity={intensity_val:.2f}): "
                    f"weight boosted to {w:.2f}"
                )
            elif agreement == 1 and rec.stance == "negative":
                reason = (
                    f"Negative stance aligned with negative emotion ({dom_emotion}, intensity={intensity_val:.2f}): "
                    f"opposition weight boosted to {w:.2f}"
                )
            elif rec.stance == "positive" and val_sign == -1:
                reason = f"Mismatch: positive stance with negative emotion ({dom_emotion}): baseline weight 1.0"
            elif rec.stance == "negative" and val_sign == 1:
                reason = f"Mismatch: negative stance with positive emotion ({dom_emotion}): baseline weight 1.0"
            else:
                reason = f"Neutral stance or neutral/ambiguous emotion ({dom_emotion}): baseline weight 1.0"

        s_weight = float(stance_weights.get(rec.stance, 0.0))
        contribution = w * s_weight

        contributions.append({
            "member": rec.member,
            "option": c_opt,
            "stance": rec.stance,
            "emotion": rec.emotion.dominant_emotion if rec.emotion else None,
            "intensity": round(intensity_val, 4) if intensity_val is not None else None,
            "agreement": agreement,
            "weight": round(w, 4),
            "contribution": round(contribution, 4),
            "reason": reason,
        })

        option_scores[c_opt] += contribution

    # Round final scores for clean representation and numerical consistency
    option_scores = {opt: round(sc, 4) for opt, sc in option_scores.items()}

    # Rank candidate options
    max_score = max(option_scores.values()) if option_scores else 0.0
    tied_options = [opt for opt, sc in option_scores.items() if sc == max_score]
    is_tie = len(tied_options) > 1

    # Break ties deterministically
    chosen = _resolve_tie(tied_options, tie_break, mention_order) if tied_options else None

    # Ranking list (ordered by score descending, then option alphabetically)
    sorted_ranking = sorted(
        [{"option": opt, "score": option_scores[opt]} for opt in candidates],
        key=lambda item: (-item["score"], item["option"]),
    )

    # Majority verification: positive votes for chosen option > 50% of voting members
    positive_votes_chosen = sum(
        1 for m, stances in member_stances.items() if stances.get(chosen) == "positive"
    )
    total_voting_members = len(member_stances)
    has_majority = (positive_votes_chosen / total_voting_members > 0.5) if total_voting_members > 0 else False

    # Check whether weighted voting flipped outcome vs preference-only
    outcome_changed = (chosen != pref_res.chosen_option)

    return DecisionResult(
        category=category,
        chosen_option=chosen,
        ranking=sorted_ranking,
        scores=option_scores,
        is_tie=is_tie,
        tied_options=sorted(tied_options) if is_tie else [],
        has_majority=has_majority,
        method="weighted",
        config=cfg,
        reason=None,
        contributions=contributions,
        outcome_changed_vs_preference_only=outcome_changed,
    )


# Register in METHODS registry
METHODS["weighted"] = weighted_vote
