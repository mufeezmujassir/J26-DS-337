"""Compute the 12 cross-turn consistency features.

The features mirror the outputs of the Progressive Preference Elicitation
(PPE) module: recorded constraints, conflicting constraints, last-stated
vibe/budget/pace, plan churn, turn counts, and conversation metadata.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Set

from app.replanning.dynamic_replanning.classifiers.consistency import (
    PACE_ENCODING,
    SCHEDULE_SHIFT_THRESHOLD_MINUTES,
    VIBE_ENCODING,
    VIBE_NONE,
    VIOLATION_BUDGET_EXCEEDED,
    VIOLATION_CONFIRMED_REMOVED,
    VIOLATION_MUST_SEE_REMOVED,
    VIOLATION_NO_RUSHING,
    VIOLATION_REJECTION_REINTRODUCED,
    VIOLATION_VIBE_MISMATCH,
    DEFAULT_SEED,
)

__all__ = [
    "extract_features",
    "detect_violations",
    "CONVERSATION_METADATA_FIELDS",
]

# Deterministic metadata fields (seed-42 randoms, stable per conversation).
CONVERSATION_METADATA_FIELDS = (
    "avg_emotion_score",
    "time_since_last_turn_minutes",
    "num_replans_this_trip",
)


def _context_rand(conversation_id: str, seed: int = DEFAULT_SEED) -> Dict[str, float]:
    """Stable per-conversation pseudo-random metadata (seed 42)."""

    digest = hashlib.sha256(f"{seed}|{conversation_id}".encode()).hexdigest()
    rng_seed = int(digest, 16) % (2**31)
    import random

    rng = random.Random(rng_seed)
    return {
        "avg_emotion_score": round(rng.uniform(0.2, 0.9), 4),
        "time_since_last_turn_minutes": rng.randint(2, 180),
        "num_replans_this_trip": rng.randint(0, 3),
    }


def detect_violations(
    conversation: Dict[str, Any], new_plan: Dict[str, Any]
) -> List[str]:
    """Return violation codes for ``new_plan`` against recorded constraints.

    Mirrors the production hard rules in ``cross_turn_consistency``.
    """

    constraints = conversation.get("constraints", {}) or {}
    violations: List[str] = []

    plan_vibe = new_plan.get("vibe")
    stated_vibe = constraints.get("vibe")
    if stated_vibe and plan_vibe and plan_vibe != stated_vibe:
        violations.append(VIOLATION_VIBE_MISMATCH)

    budget = constraints.get("budget_usd")
    total_cost = new_plan.get("total_cost_usd")
    if budget is not None and total_cost is not None:
        if float(total_cost) > float(budget) + 1e-9:
            violations.append(VIOLATION_BUDGET_EXCEEDED)

    plan_names = _plan_names(new_plan)

    must_see = set(constraints.get("must_see", []) or [])
    if any(name not in plan_names for name in must_see):
        violations.append(VIOLATION_MUST_SEE_REMOVED)

    confirmations = set(conversation.get("confirmations", []) or [])
    if any(name not in plan_names for name in confirmations):
        violations.append(VIOLATION_CONFIRMED_REMOVED)

    rejections = set(conversation.get("rejections", []) or []) - confirmations
    if any(name in plan_names for name in rejections):
        violations.append(VIOLATION_REJECTION_REINTRODUCED)

    if constraints.get("no_rushing"):
        shift = _max_schedule_shift(conversation, new_plan)
        if shift > SCHEDULE_SHIFT_THRESHOLD_MINUTES:
            violations.append(VIOLATION_NO_RUSHING)

    return violations


def extract_features(conversation: Dict[str, Any], new_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return the 12 consistency features for (conversation, new_plan)."""

    constraints = conversation.get("constraints", {}) or {}
    rand = _context_rand(conversation.get("conversation_id", "conv_unknown"))

    num_prior_constraints = _count_constraints(constraints, conversation)
    violations = detect_violations(conversation, new_plan)
    num_conflicting = len(violations)

    last_vibe = constraints.get("vibe")
    last_vibe_mentioned = VIBE_ENCODING.get(last_vibe, VIBE_NONE) if last_vibe else VIBE_NONE

    last_budget_mentioned = float(constraints.get("budget_usd", 0.0) or 0.0)

    last_pace = constraints.get("pace")
    last_pace_preference = PACE_ENCODING.get(last_pace, 1)

    plan_changes = _plan_changes_since_last_turn(conversation, new_plan)

    num_turns = int(conversation.get("num_turns", 0) or 0)
    num_confirmations = len(conversation.get("confirmations", []) or [])
    num_rejections = len(conversation.get("rejections", []) or [])

    return {
        "num_prior_constraints": num_prior_constraints,
        "num_conflicting_constraints": num_conflicting,
        "last_vibe_mentioned": int(last_vibe_mentioned),
        "last_budget_mentioned": round(last_budget_mentioned, 2),
        "last_pace_preference": int(last_pace_preference),
        "plan_changes_since_last_turn": plan_changes,
        "num_turns": num_turns,
        "avg_emotion_score": float(rand["avg_emotion_score"]),
        "num_explicit_confirmations": num_confirmations,
        "num_explicit_rejections": num_rejections,
        "time_since_last_turn_minutes": int(rand["time_since_last_turn_minutes"]),
        "num_replans_this_trip": int(rand["num_replans_this_trip"]),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan_names(plan: Dict[str, Any]) -> Set[str]:
    return {str(a.get("name", "")) for a in plan.get("activities", []) or []}


def _count_constraints(
    constraints: Dict[str, Any], conversation: Dict[str, Any]
) -> int:
    count = 0
    if constraints.get("vibe"):
        count += 1
    if constraints.get("budget_usd") is not None:
        count += 1
    if constraints.get("pace"):
        count += 1
    count += len(constraints.get("must_see", []) or [])
    if constraints.get("no_rushing"):
        count += 1
    count += len(conversation.get("confirmations", []) or [])
    return count


def _plan_changes_since_last_turn(
    conversation: Dict[str, Any], new_plan: Dict[str, Any]
) -> int:
    initial = conversation.get("initial_plan", {}) or {}
    initial_ids = {
        a.get("attraction_id") for a in initial.get("activities", []) or []
    }
    new_ids = {a.get("attraction_id") for a in new_plan.get("activities", []) or []}
    return len(initial_ids.symmetric_difference(new_ids))


def _max_schedule_shift(
    conversation: Dict[str, Any], new_plan: Dict[str, Any]
) -> float:
    initial = conversation.get("initial_plan", {}) or {}
    initial_by_id = {
        a.get("attraction_id"): int(a.get("start_minutes", 0))
        for a in initial.get("activities", []) or []
    }
    max_shift = 0.0
    for activity in new_plan.get("activities", []) or []:
        attraction_id = activity.get("attraction_id")
        if attraction_id in initial_by_id:
            shift = abs(
                int(activity.get("start_minutes", 0))
                - initial_by_id[attraction_id]
            )
            max_shift = max(max_shift, float(shift))
    return max_shift
