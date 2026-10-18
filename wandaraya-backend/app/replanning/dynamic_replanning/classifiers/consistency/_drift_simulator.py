"""Simulate intent-drift events and consistent plan alternatives.

Given a conversation (with PPE-extracted constraints, confirmations and
rejections plus the current plan), produce either a drifted new plan that
violates one recorded constraint, or a consistent alternative that respects
every constraint.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.classifiers.consistency import (
    ACTIVITY_COST_RANGE_USD,
    DRIFT_BUDGET_EXCEEDED,
    DRIFT_CONSTRAINT_CONTRADICTION,
    DRIFT_CONFIRMED_MUST_SEE_REMOVED,
    DRIFT_NO_RUSHING_VIOLATED,
    DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED,
    DRIFT_TYPES,
    DRIFT_VIBE_CHANGED,
    HOTEL_COST_PER_NIGHT_USD,
    SCHEDULE_SHIFT_THRESHOLD_MINUTES,
    TRANSPORT_COST_PER_DAY_USD,
    DEFAULT_SEED,
)

from app.replanning.dynamic_replanning.classifiers.consistency._conversation_generator import (
    ConversationGenerator,
)

LOGGER = logging.getLogger(__name__)

# Vibes that "contradict" each other for the constraint-contradiction scenario.
CONTRADICTORY_VIBE: Dict[str, str] = {
    "relaxed": "active",
    "active": "relaxed",
    "cultural": "active",
    "mixed": "cultural",
}


class DriftSimulator:
    """Inject one drift scenario into a conversation, or keep it consistent."""

    def __init__(
        self,
        seed: int = DEFAULT_SEED,
        generator: Optional[ConversationGenerator] = None,
    ) -> None:
        self.seed = seed
        self.generator = generator

    def feasible_drift_types(self, conversation: Dict[str, Any]) -> List[str]:
        """Return drift types that can produce a detectable violation here."""

        constraints = conversation.get("constraints", {}) or {}
        feasible = [
            DRIFT_CONSTRAINT_CONTRADICTION,
            DRIFT_VIBE_CHANGED,
            DRIFT_BUDGET_EXCEEDED,
        ]
        protected = set(constraints.get("must_see", [])) | set(
            conversation.get("confirmations", [])
        )
        if protected:
            feasible.append(DRIFT_CONFIRMED_MUST_SEE_REMOVED)
        if conversation.get("rejections"):
            feasible.append(DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED)
        if constraints.get("no_rushing"):
            feasible.append(DRIFT_NO_RUSHING_VIOLATED)
        return feasible

    def inject_drift(
        self,
        conversation: Dict[str, Any],
        drift_type: Optional[str] = None,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """Return ``{"drift_type", "new_plan"}`` with one drift applied."""

        rng = rng or random.Random(f"{self.seed}|{conversation['conversation_id']}")
        feasible = self.feasible_drift_types(conversation)
        if drift_type is None:
            drift_type = rng.choice(feasible)
        elif drift_type not in feasible:
            # The requested scenario has no precondition to violate here
            # (e.g. no-rushing drift on a fast-paced conversation); use a
            # always-feasible contradiction instead.
            LOGGER.debug(
                "Drift type %s infeasible for %s; falling back",
                drift_type,
                conversation.get("conversation_id"),
            )
            drift_type = DRIFT_CONSTRAINT_CONTRADICTION

        handler = {
            DRIFT_CONSTRAINT_CONTRADICTION: self._drift_constraint_contradiction,
            DRIFT_CONFIRMED_MUST_SEE_REMOVED: self._drift_confirmed_removed,
            DRIFT_VIBE_CHANGED: self._drift_vibe_changed,
            DRIFT_BUDGET_EXCEEDED: self._drift_budget_exceeded,
            DRIFT_NO_RUSHING_VIOLATED: self._drift_no_rushing,
            DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED: self._drift_rejection_reintroduced,
        }[drift_type]

        new_plan = handler(conversation, rng)
        LOGGER.debug(
            "Injected drift '%s' into %s",
            drift_type,
            conversation.get("conversation_id"),
        )
        return {"drift_type": drift_type, "new_plan": new_plan}

    def produce_consistent_alternative(
        self,
        conversation: Dict[str, Any],
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """Return a new plan that respects every recorded constraint."""

        rng = rng or random.Random(
            f"{self.seed}|consistent|{conversation['conversation_id']}"
        )
        plan = conversation["initial_plan"]
        constraints = conversation["constraints"]

        rejections = (
            set(conversation.get("rejections", []) or [])
            - set(conversation.get("confirmations", []) or [])
            - set(constraints.get("must_see", []) or [])
        )
        # A consistent follow-up plan honours rejections: drop them.
        activities = [
            dict(a) for a in plan["activities"] if a["name"] not in rejections
        ]
        if not activities:
            activities = [dict(a) for a in plan["activities"]]
        used = {a["name"] for a in activities}
        must_keep = set(constraints.get("must_see", [])) | set(
            conversation.get("confirmations", [])
        )
        banned = must_keep | set(conversation.get("rejections", []))

        # Swap up to two unconfirmed, non-must-see activities for variety.
        swappable = [
            a for a in activities if a["name"] not in must_keep
        ]
        for _ in range(min(2, len(swappable))):
            if self.generator is None or rng.random() < 0.5:
                continue
            target = rng.choice(swappable)
            replacement = self.generator.pick_attraction(
                rng,
                conversation["persona"],
                exclude=used | banned,
            )
            if replacement is None:
                continue
            used.discard(target["name"])
            used.add(replacement["name"])
            activities = [
                _replace_activity(
                    a, target, replacement, rng, keep_duration=True
                )
                if a is target
                else a
                for a in activities
            ]
            swappable = [a for a in swappable if a is not target]

        new_plan = {
            **plan,
            "plan_id": f"{plan['plan_id']}_alt",
            "vibe": constraints["vibe"],
            "activities": activities,
        }
        new_plan["total_cost_usd"] = _recompute_cost(new_plan)
        _ensure_within_budget(new_plan, constraints, rng)
        _ensure_schedule_comfortable(new_plan, constraints)
        return new_plan

    # ------------------------------------------------------------------
    # Drift scenarios
    # ------------------------------------------------------------------

    def _drift_constraint_contradiction(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Propose a plan whose vibe contradicts the stated constraint."""

        constraints = conversation["constraints"]
        plan = conversation["initial_plan"]
        wrong_vibe = CONTRADICTORY_VIBE.get(
            constraints["vibe"], "active"
        )

        activities = [dict(a) for a in plan["activities"]]
        used = {a["name"] for a in activities}
        if self.generator is not None:
            for index in range(max(1, len(activities) // 2)):
                target = activities[index]
                replacement = self.generator.pick_attraction(
                    rng, conversation["persona"], exclude=used
                )
                if replacement is None:
                    continue
                # Force a category that does not match the stated vibe.
                replacement = _force_wrong_category(
                    self.generator, rng, wrong_vibe, used
                ) or replacement
                used.discard(target["name"])
                used.add(replacement["name"])
                activities[index] = _replace_activity(
                    target, target, replacement, rng
                )

        new_plan = {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "vibe": wrong_vibe,
            "activities": activities,
        }
        new_plan["total_cost_usd"] = _recompute_cost(new_plan)
        return new_plan

    def _drift_confirmed_removed(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Remove a must-see the user explicitly confirmed."""

        plan = conversation["initial_plan"]
        constraints = conversation["constraints"]
        protected = set(constraints.get("must_see", [])) | set(
            conversation.get("confirmations", [])
        )
        removable = [
            a for a in plan["activities"] if a["name"] in protected
        ] or list(plan["activities"])

        target = rng.choice(removable) if removable else None
        activities = [dict(a) for a in plan["activities"] if a is not target]
        if not activities and plan["activities"]:
            activities = [dict(a) for a in plan["activities"][1:]]
            target = plan["activities"][0]

        new_plan = {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "activities": activities,
            "removed_activity": target["name"] if target else None,
        }
        new_plan["total_cost_usd"] = _recompute_cost(new_plan)
        return new_plan

    def _drift_vibe_changed(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Change the plan vibe without user approval."""

        plan = conversation["initial_plan"]
        constraints = conversation["constraints"]
        current = constraints["vibe"]
        alternatives = [v for v in ("relaxed", "active", "cultural", "mixed") if v != current]
        new_vibe = rng.choice(alternatives)
        return {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "vibe": new_vibe,
            "activities": [dict(a) for a in plan["activities"]],
        }

    def _drift_budget_exceeded(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Push the plan cost beyond the user's stated budget limit."""

        plan = conversation["initial_plan"]
        constraints = conversation["constraints"]
        budget = float(constraints.get("budget_usd", plan.get("budget_usd", 0.0)))

        activities = [dict(a) for a in plan["activities"]]
        used = {a["name"] for a in activities}
        if self.generator is not None:
            # Add an extra expensive day-trip block until budget is breached.
            for _ in range(3):
                attraction = self.generator.pick_attraction(
                    rng, conversation["persona"], exclude=used
                )
                if attraction is None:
                    break
                used.add(attraction["name"])
                activities.append(
                    {
                        "attraction_id": attraction["attraction_id"],
                        "name": attraction["name"],
                        "district": attraction["district"],
                        "category": attraction["category"],
                        "day": len({a["day"] for a in activities}) + 1,
                        "start_minutes": 540,
                        "duration_minutes": int(
                            attraction.get("duration_minutes") or 120
                        ),
                        "entry_fee_usd": float(
                            attraction.get("entry_fee_usd", 0.0)
                        ),
                        "activity_cost_usd": round(budget / 2.0, 2),
                    }
                )
                total = _recompute_cost({**plan, "activities": activities})
                if total > budget:
                    break

        new_plan = {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "activities": activities,
        }
        new_plan["total_cost_usd"] = _recompute_cost(new_plan)
        if new_plan["total_cost_usd"] <= budget:
            # Guarantee the violation even if additions were impossible.
            new_plan["total_cost_usd"] = round(budget * 1.25, 2)
        return new_plan

    def _drift_no_rushing(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Violate a 'no rushing' constraint with a large schedule shift."""

        plan = conversation["initial_plan"]
        constraints = conversation["constraints"]
        shift = SCHEDULE_SHIFT_THRESHOLD_MINUTES + rng.randint(15, 90)

        activities = []
        for activity in plan["activities"]:
            item = dict(activity)
            item["start_minutes"] = max(
                0, int(item["start_minutes"]) - shift
            )
            item["duration_minutes"] = max(
                30, int(item["duration_minutes"]) - rng.randint(30, 60)
            )
            activities.append(item)

        return {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "activities": activities,
            "schedule_shift_minutes": shift,
        }

    def _drift_rejection_reintroduced(
        self, conversation: Dict[str, Any], rng: random.Random
    ) -> Dict[str, Any]:
        """Reintroduce an alternative the user already rejected."""

        plan = conversation["initial_plan"]
        rejections = conversation.get("rejections", [])
        activities = [dict(a) for a in plan["activities"]]

        if rejections and self.generator is not None:
            rejected_name = rng.choice(rejections)
            attraction = self.generator.pick_attraction(
                rng,
                conversation["persona"],
                exclude={a["name"] for a in activities},
            )
            # Find a real attraction matching the rejected name, else synthesise.
            target = next(
                (
                    a
                    for a in self.generator.attractions
                    if a["name"] == rejected_name
                ),
                None,
            )
            replacement = target or attraction
            if replacement is not None and activities:
                used = {a["name"] for a in activities}
                used.add(replacement["name"])
                victim = activities[-1]
                activities[-1] = _replace_activity(
                    victim, victim, replacement, rng
                )

        return {
            **plan,
            "plan_id": f"{plan['plan_id']}_drift",
            "activities": activities,
            "reintroduced_rejection": (
                rejections[0] if rejections else None
            ),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _replace_activity(
    original: Dict[str, Any],
    _target: Dict[str, Any],
    attraction: Dict[str, Any],
    rng: random.Random,
    keep_duration: bool = False,
) -> Dict[str, Any]:
    """Return ``original``'s slot filled with a new real attraction."""

    return {
        **original,
        "attraction_id": attraction["attraction_id"],
        "name": attraction["name"],
        "district": attraction["district"],
        "category": attraction["category"],
        "duration_minutes": int(
            original["duration_minutes"]
            if keep_duration
            else (attraction.get("duration_minutes") or 120)
        ),
        "entry_fee_usd": float(attraction.get("entry_fee_usd", 0.0)),
        "activity_cost_usd": round(
            rng.uniform(*ACTIVITY_COST_RANGE_USD), 2
        ),
    }


def _recompute_cost(plan: Dict[str, Any]) -> float:
    fixed_daily = HOTEL_COST_PER_NIGHT_USD + TRANSPORT_COST_PER_DAY_USD
    trip_days = max(
        (int(a.get("day", 1)) for a in plan.get("activities", [])), default=1
    )
    total = fixed_daily * trip_days + sum(
        float(a.get("activity_cost_usd", 0.0)) for a in plan.get("activities", [])
    )
    return round(total, 2)


def _ensure_within_budget(
    plan: Dict[str, Any], constraints: Dict[str, Any], rng: random.Random
) -> None:
    """Scale activity costs down until the plan fits the stated budget.

    Never drops activities (dropping could remove a confirmed must-see and
    turn a consistent alternative into a violation).
    """

    budget = float(constraints.get("budget_usd", plan.get("budget_usd", 0.0)))
    activities = plan.get("activities", [])
    if plan["total_cost_usd"] <= budget or not activities:
        return

    trip_days = max((int(a.get("day", 1)) for a in activities), default=1)
    fixed = (HOTEL_COST_PER_NIGHT_USD + TRANSPORT_COST_PER_DAY_USD) * trip_days
    available = max(0.0, budget - fixed)
    current_variable_costs = sum(
        float(a.get("activity_cost_usd", 0.0)) for a in activities
    )
    if current_variable_costs <= 0:
        plan["total_cost_usd"] = _recompute_cost(plan)
        return

    scale = available / current_variable_costs
    for activity in activities:
        activity["activity_cost_usd"] = round(
            float(activity["activity_cost_usd"]) * scale, 2
        )
    plan["total_cost_usd"] = _recompute_cost(plan)


def _ensure_schedule_comfortable(
    plan: Dict[str, Any], constraints: Dict[str, Any]
) -> None:
    """Keep schedule shifts within the 'no rushing' threshold."""

    if not constraints.get("no_rushing"):
        return
    by_day: Dict[int, List[Dict[str, Any]]] = {}
    for activity in plan["activities"]:
        by_day.setdefault(int(activity["day"]), []).append(activity)
    for day_activities in by_day.values():
        day_activities.sort(key=lambda a: int(a["start_minutes"]))
        previous_end = None
        for activity in day_activities:
            start = int(activity["start_minutes"])
            if previous_end is not None and start < previous_end:
                activity["start_minutes"] = previous_end
            previous_end = int(activity["start_minutes"]) + int(
                activity["duration_minutes"]
            )


def _force_wrong_category(
    generator: ConversationGenerator,
    rng: random.Random,
    vibe: str,
    used: set,
) -> Optional[Dict[str, Any]]:
    """Pick an attraction whose category is unlikely for ``vibe``."""

    vibe_preferred = {
        "active": {"Nature & Landscapes", "Wildlife & Safari"},
        "cultural": {"History & Archaeology", "Culture & Heritage"},
        "relaxed": {"Beaches & Coastal", "Wellness & Ayurveda"},
        "mixed": set(),
    }.get(vibe, set())

    pool = [
        a
        for a in generator.attractions
        if a["name"] not in used and a["category"] not in vibe_preferred
    ]
    if not pool:
        return None
    return rng.choice(pool)


__all__ = ["DriftSimulator"]
