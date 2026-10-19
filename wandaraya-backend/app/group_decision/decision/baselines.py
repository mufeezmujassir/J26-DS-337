"""Decision Engine Baselines.

Implements majority voting and preference-only baseline decision methods.
Deterministic, modular, and configurable via configs/config.yaml.

"""

from __future__ import annotations

import logging
from pathlib import Path
import random
from typing import Any, Callable
import yaml

from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.schemas import DecisionResult, PreferenceRecord

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "config.yaml"


def set_seed(seed: int = 42) -> None:
    """Set random seed for reproducibility across libraries if needed."""
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


def load_decision_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load decision configuration from config.yaml."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    defaults = {
        "categories": ["Destination", "Activity"],
        "majority_policy": "split",  
        "tie_break": "alphabetical",  
        "negative_veto": False,
        "stance_weights": {
            "positive": 1.0,
            "neutral": 0.0,
            "negative": -1.0,
        },
    }

    if not path.exists():
        fallback = Path("configs/config.yaml")
        if fallback.exists():
            path = fallback
        else:
            logger.warning("Config path %s not found. Using defaults.", path)
            return defaults

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    decision_cfg = data.get("decision", {})
    # Merge defaults
    for k, v in defaults.items():
        if k not in decision_cfg:
            decision_cfg[k] = v
        elif isinstance(v, dict) and isinstance(decision_cfg[k], dict):
            merged = dict(v)
            merged.update(decision_cfg[k])
            decision_cfg[k] = merged

    return decision_cfg


def _deduplicate_records(
    records: list[Any],
    category: str,
) -> tuple[list[PreferenceRecord], list[str]]:
    """Validate records, resolve repeated records per (member, category, name),

    and return the active deduplicated records and the original candidate appearance order.
    """
    validated: list[PreferenceRecord] = []
    for raw in records:
        if isinstance(raw, PreferenceRecord):
            validated.append(raw)
        else:
            validated.append(PreferenceRecord.model_validate(raw))

    dedup_map: dict[tuple[str, str, str], PreferenceRecord] = {}
    mention_order: list[str] = []

    for rec in validated:
        if rec.category != category:
            continue

        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if not opt_raw:
            continue

        canon_name = normalize_name(opt_raw, category=category)
        if canon_name not in mention_order:
            mention_order.append(canon_name)

        key = (rec.member, rec.category, canon_name)
        if key in dedup_map:
            logger.warning(
                "Member '%s' has contradictory/repeated records for %s '%s'; keeping latest record.",
                rec.member,
                rec.category,
                canon_name,
            )
        dedup_map[key] = rec

    return list(dedup_map.values()), mention_order


def _resolve_tie(
    tied_options: list[str],
    tie_break: str,
    mention_order: list[str],
) -> str:
    """Break a tie deterministically according to configured policy.

    # Note: A tie-break is arbitrary and results with ties must be reported as ties.
    """
    if not tied_options:
        return ""

    if tie_break == "first_mentioned":
        for opt in mention_order:
            if opt in tied_options:
                return opt
        return sorted(tied_options)[0]

    # Default: alphabetical
    return sorted(tied_options)[0]


def majority_vote(
    records: list[Any],
    category: str = "Destination",
    candidate_options: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> DecisionResult:
    """Method 1: Majority voting.

    Each member has exactly one vote per category. Only positive stances count.
    A member with several positive options splits their one vote equally across
    them (policy 'split' default, or 'latest' which uses the last positive record).
    Negative and neutral stances give no vote. The option with the most votes wins.
    """
    set_seed(42)
    cfg = config or {}
    policy = cfg.get("majority_policy", "split")
    tie_break = cfg.get("tie_break", "alphabetical")

    active_records, mention_order = _deduplicate_records(records, category)

    # Determine candidates
    if candidate_options is not None:
        candidates = [normalize_name(opt, category=category) for opt in candidate_options]
    else:
        candidates = list(mention_order)

    # Ensure deterministic uniqueness of candidates
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
            method="majority",
            config=cfg,
            reason="Empty records input or no candidates found",
        )

    # Gather positive options per member
    member_positives: dict[str, list[str]] = {}
    for rec in active_records:
        if rec.stance == "positive":
            val = rec.value
            opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
            if opt_raw:
                c_opt = normalize_name(opt_raw, category=category)
                if c_opt in candidates:
                    if rec.member not in member_positives:
                        member_positives[rec.member] = []
                    member_positives[rec.member].append(c_opt)

    # Edge case 2: No positive preferences in category
    if not member_positives:
        return DecisionResult(
            category=category,
            chosen_option=None,
            ranking=[{"option": c, "score": 0.0} for c in candidates],
            scores={c: 0.0 for c in candidates},
            is_tie=False,
            tied_options=[],
            has_majority=False,
            method="majority",
            config=cfg,
            reason="No positive preferences in category",
        )

    # Tally votes
    scores: dict[str, float] = {c: 0.0 for c in candidates}
    total_votes = 0.0

    for member, opts in member_positives.items():
        if not opts:
            continue
        if policy == "latest":
            # Last positive option in record order gets full 1.0 vote
            chosen_single = opts[-1]
            scores[chosen_single] += 1.0
            total_votes += 1.0
        else:
            
            distinct_opts = list(dict.fromkeys(opts))
            share = 1.0 / len(distinct_opts)
            for opt in distinct_opts:
                scores[opt] += share
            total_votes += 1.0

    # Round scores for clean presentation
    scores = {k: round(v, 4) for k, v in scores.items()}

    # Rank candidates by score descending, then tie_break order
    max_score = max(scores.values()) if scores else 0.0
    tied_options = [opt for opt, score in scores.items() if score == max_score and max_score > 0.0]

    is_tie = len(tied_options) > 1
    # Note: A tie-break is arbitrary and results with ties must be reported as ties.
    chosen = _resolve_tie(tied_options, tie_break, mention_order) if tied_options else None

    # Ranking list
    sorted_ranking = sorted(
        [{"option": opt, "score": score} for opt, score in scores.items()],
        key=lambda item: (-item["score"], item["option"]),
    )

    # Has majority: winner's share of total votes strictly above 0.5
    winner_score = scores.get(chosen, 0.0) if chosen else 0.0
    has_majority = (winner_score / total_votes > 0.5) if total_votes > 0 else False

    return DecisionResult(
        category=category,
        chosen_option=chosen,
        ranking=sorted_ranking,
        scores=scores,
        is_tie=is_tie,
        tied_options=sorted(tied_options) if is_tie else [],
        has_majority=has_majority,
        method="majority",
        config=cfg,
        reason=None,
    )


def preference_only(
    records: list[Any],
    category: str = "Destination",
    candidate_options: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> DecisionResult:
    """Method 2: Preference-only aggregation.

    score(option) = sum over members of stance_weight[stance],
    with defaults positive +1, neutral 0, negative -1. Highest score wins.
    Optional flag negative_veto (default false): when true, options rejected
    by any member are excluded unless every option is rejected.
    """
    set_seed(42)
    cfg = config or {}
    tie_break = cfg.get("tie_break", "alphabetical")
    negative_veto = cfg.get("negative_veto", False)
    weights = cfg.get("stance_weights", {"positive": 1.0, "neutral": 0.0, "negative": -1.0})

    active_records, mention_order = _deduplicate_records(records, category)

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
            method="preference_only",
            config=cfg,
            reason="Empty records input or no candidates found",
        )

    # Check if ANY positive stance exists across category
    has_any_positive = any(r.stance == "positive" for r in active_records)
    if not has_any_positive:
        # No positive stance in category
        return DecisionResult(
            category=category,
            chosen_option=None,
            ranking=[{"option": c, "score": 0.0} for c in candidates],
            scores={c: 0.0 for c in candidates},
            is_tie=False,
            tied_options=[],
            has_majority=False,
            method="preference_only",
            config=cfg,
            reason="No positive preferences in category",
        )

    # Map member -> option -> stance
    member_stances: dict[str, dict[str, str]] = {}
    rejected_options: set[str] = set()

    for rec in active_records:
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if opt_raw:
            c_opt = normalize_name(opt_raw, category=category)
            if c_opt in candidates:
                if rec.member not in member_stances:
                    member_stances[rec.member] = {}
                member_stances[rec.member][c_opt] = rec.stance
                if rec.stance == "negative":
                    rejected_options.add(c_opt)

    # Compute scores for all candidate options
    scores: dict[str, float] = {c: 0.0 for c in candidates}
    for opt in candidates:
        opt_score = 0.0
        for m, stances in member_stances.items():
            stance = stances.get(opt, "neutral")
            opt_score += float(weights.get(stance, 0.0))
        scores[opt] = round(opt_score, 4)

    # Handle negative_veto
    eligible_candidates = list(candidates)
    if negative_veto:
        non_vetoed = [c for c in candidates if c not in rejected_options]
        # "unless every option is rejected"
        if non_vetoed:
            eligible_candidates = non_vetoed
        else:
            eligible_candidates = list(candidates)

    eligible_scores = {c: scores[c] for c in eligible_candidates}
    max_score = max(eligible_scores.values()) if eligible_scores else 0.0
    tied_options = [opt for opt, score in eligible_scores.items() if score == max_score]

    is_tie = len(tied_options) > 1
    # Note: A tie-break is arbitrary and results with ties must be reported as ties.
    chosen = _resolve_tie(tied_options, tie_break, mention_order) if tied_options else None

    # Ranking list (ordered by scores descending)
    sorted_ranking = sorted(
        [{"option": opt, "score": scores[opt]} for opt in candidates],
        key=lambda item: (-item["score"], item["option"]),
    )

    # Check majority of positive votes for chosen option
    positive_votes_chosen = sum(
        1 for m, stances in member_stances.items() if stances.get(chosen) == "positive"
    )
    total_voting_members = len(member_stances)
    has_majority = (positive_votes_chosen / total_voting_members > 0.5) if total_voting_members > 0 else False

    return DecisionResult(
        category=category,
        chosen_option=chosen,
        ranking=sorted_ranking,
        scores=scores,
        is_tie=is_tie,
        tied_options=sorted(tied_options) if is_tie else [],
        has_majority=has_majority,
        method="preference_only",
        config=cfg,
        reason=None,
    )


METHODS: dict[str, Callable[..., DecisionResult]] = {
    "majority": majority_vote,
    "preference_only": preference_only,
}


def decide(
    records: list[Any],
    method: str,
    category: str | None = None,
    candidate_options: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> DecisionResult:
    """Common interface for executing decision baselines.

    Args:
        records: List of structured preference records.
        method: Decision method ('majority' or 'preference_only').
        category: Category to decide on ('Destination' or 'Activity').
                  If None, inferred from records or defaults to 'Destination'.
        candidate_options: Optional explicit list of candidate option strings.
        config: Optional configuration overrides.

    Returns:
        DecisionResult instance.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown decision method '{method}'. Available methods: {sorted(METHODS.keys())}")

    # Load system config and overlay caller overrides
    base_cfg = load_decision_config()
    if config:
        base_cfg.update(config)

    # Determine category
    chosen_cat = category
    if chosen_cat is None:
        chosen_cat = base_cfg.get("category")
    if chosen_cat is None:
        # Infer from records
        cats_in_records = []
        for raw in records:
            cat = getattr(raw, "category", None) or (raw.get("category") if isinstance(raw, dict) else None)
            if cat in ("Destination", "Activity") and cat not in cats_in_records:
                cats_in_records.append(cat)
        chosen_cat = cats_in_records[0] if cats_in_records else "Destination"

    fn = METHODS[method]
    return fn(
        records=records,
        category=chosen_cat,
        candidate_options=candidate_options,
        config=base_cfg,
    )
