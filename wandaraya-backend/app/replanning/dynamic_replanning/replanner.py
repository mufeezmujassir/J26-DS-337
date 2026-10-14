"""Dynamic Replanner orchestrating the rule-based replanning pipeline."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.alternative_finder import (
    AlternativeFinder,
)
from app.replanning.dynamic_replanning.confirmation_flow import (
    ConfirmationFlow,
)
from app.replanning.dynamic_replanning.cross_turn_consistency import (
    CrossTurnConsistency,
)
from app.replanning.dynamic_replanning.intent_preserver import (
    IntentPreserver,
)
from app.replanning.dynamic_replanning.state_manager import (
    ReplanningStateManager,
)
from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    format_revised_plan,
    load_config,
)
from app.schemas.replanning import (
    AffectedElement,
    ConfirmationResult,
    IntentAnchor,
    RevisedActivity,
    RevisedPlan,
)

LOGGER = logging.getLogger(__name__)


class DynamicReplanner:
    """Orchestrate rule-based dynamic replanning."""

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._config_path = config_path
        try:
            self._config = load_config(config_path)
        except (FileNotFoundError, ValueError) as error:
            LOGGER.warning(
                "Could not load config from %s (%s), using defaults",
                config_path,
                error,
            )
            self._config = DEFAULT_CONFIG

        self._state_manager = ReplanningStateManager(config=self._config)
        self._intent_preserver = IntentPreserver(config=self._config)
        self._alternative_finder = AlternativeFinder(config=self._config)
        self._consistency_checker = CrossTurnConsistency(config=self._config)
        self._confirmation_flow = ConfirmationFlow(state_manager=self._state_manager)

        LOGGER.info("DynamicReplanner initialised")

    def replan(
        self,
        disruption: Dict[str, Any],
        user_id: str,
        original_itinerary: Dict[str, Any],
    ) -> RevisedPlan:
        LOGGER.info(
            "Replanning for user %s (disruption_id=%s)",
            user_id,
            disruption.get("disruption_id") or "n/a",
        )

        anchor = self._state_manager.get_intent_anchor(user_id)
        if anchor is None:
            anchor = self._build_anchor(user_id, original_itinerary)
            self._state_manager.set_intent_anchor(user_id, anchor)
            LOGGER.info("Created intent anchor for user %s", user_id)

        severity = (disruption.get("severity") or "step").lower()
        if severity not in ("step", "day", "plan"):
            severity = "step"

        if severity == "step":
            revised = self.replan_step_level(disruption, user_id, original_itinerary)
        elif severity == "day":
            revised = self.replan_day_level(disruption, user_id, original_itinerary)
        else:
            revised = self.replan_plan_level(disruption, user_id, original_itinerary)

        try:
            self._state_manager.update_current_plan(user_id, revised)
        except Exception as error:  # noqa: BLE001
            LOGGER.debug("Failed to persist current plan: %s", error)

        try:
            preserved = self._intent_preserver.preserve(original_itinerary, revised, anchor)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Intent preservation failed: %s", error)
            preserved = {
                "is_preserved": True,
                "preserved_elements": ["vibe", "budget", "bookings"],
                "broken_elements": [],
                "recommendation": "Proceed to confirmation.",
            }

        try:
            _ = self._consistency_checker.check_consistency(user_id, revised, anchor)
        except Exception as error:  # noqa: BLE001
            LOGGER.debug("Consistency check failed: %s", error)

        try:
            _ = self._confirmation_flow.present(user_id, revised, preserved)
        except Exception as error:  # noqa: BLE001
            LOGGER.debug("Confirmation presentation failed: %s", error)

        LOGGER.info("Replan complete for user %s: plan_id=%s", user_id, revised.plan_id)
        return revised

    def replan_step_level(
        self,
        disruption: Dict[str, Any],
        user_id: str,
        original_itinerary: Dict[str, Any],
    ) -> RevisedPlan:
        LOGGER.info("Step-Level replanning for user %s", user_id)

        anchor = self._state_manager.get_intent_anchor(user_id) or self._build_anchor(user_id, original_itinerary)
        affected_elem = self._extract_affected(disruption)

        context = {
            "original_itinerary": original_itinerary,
            "severity": "step",
        }

        try:
            alts = self._alternative_finder.find_for_step_level(affected_elem, anchor, context)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Alternative finder failed (step): %s", error)
            alts = []

        revised_activities = self._alts_to_activities(alts, "Step-Level replacement")

        revised = RevisedPlan(
            original_plan_id=str(original_itinerary.get("plan_id", "")),
            disruption_id=str(disruption.get("disruption_id", "")),
            severity="step",
            affected_element=affected_elem,
            revised_activities=revised_activities,
            preserved_elements=self._intent_preserver.get_preserved_elements(original_itinerary, RevisedPlan.model_construct(severity="step", affected_element=affected_elem), anchor) or ["vibe", "budget", "bookings"],
            requires_confirmation=True,
        )
        return revised

    def replan_day_level(
        self,
        disruption: Dict[str, Any],
        user_id: str,
        original_itinerary: Dict[str, Any],
    ) -> RevisedPlan:
        LOGGER.info("Day-Level replanning for user %s", user_id)

        anchor = self._state_manager.get_intent_anchor(user_id) or self._build_anchor(user_id, original_itinerary)
        affected_elem = self._extract_affected(disruption)
        affected_day = affected_elem.day or str(disruption.get("day", "")) or "unknown"

        context = {
            "original_itinerary": original_itinerary,
            "severity": "day",
            "affected_day": affected_day,
        }

        try:
            alts = self._alternative_finder.find_for_day_level(affected_day, anchor, context)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Alternative finder failed (day): %s", error)
            alts = []

        revised_activities = self._alts_to_activities(alts, "Day-Level replacement")

        revised = RevisedPlan(
            original_plan_id=str(original_itinerary.get("plan_id", "")),
            disruption_id=str(disruption.get("disruption_id", "")),
            severity="day",
            affected_element=affected_elem,
            revised_activities=revised_activities,
            preserved_elements=self._intent_preserver.get_preserved_elements(original_itinerary, RevisedPlan.model_construct(severity="day", affected_element=affected_elem), anchor) or ["vibe", "budget", "bookings"],
            requires_confirmation=True,
        )
        return revised

    def replan_plan_level(
        self,
        disruption: Dict[str, Any],
        user_id: str,
        original_itinerary: Dict[str, Any],
    ) -> RevisedPlan:
        LOGGER.info("Plan-Level replanning for user %s", user_id)

        anchor = self._state_manager.get_intent_anchor(user_id) or self._build_anchor(user_id, original_itinerary)
        affected_elem = self._extract_affected(disruption)

        context = {
            "original_itinerary": original_itinerary,
            "severity": "plan",
        }

        try:
            alts = self._alternative_finder.find_for_plan_level(disruption, anchor, context)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Alternative finder failed (plan): %s", error)
            alts = []

        revised_activities = self._alts_to_activities(alts, "Plan-Level replacement")

        revised = RevisedPlan(
            original_plan_id=str(original_itinerary.get("plan_id", "")),
            disruption_id=str(disruption.get("disruption_id", "")),
            severity="plan",
            affected_element=affected_elem,
            revised_activities=revised_activities,
            preserved_elements=self._intent_preserver.get_preserved_elements(original_itinerary, RevisedPlan.model_construct(severity="plan", affected_element=affected_elem), anchor) or ["vibe", "budget", "bookings"],
            requires_confirmation=True,
        )
        return revised

    def confirm(self, user_id: str, revised_plan: RevisedPlan) -> ConfirmationResult:
        try:
            return self._confirmation_flow.get_user_confirmation(user_id)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Confirmation failed: %s", error)
            return ConfirmationResult(accepted=False, user_feedback="Confirmation error", next_action="find_alternative")

    def apply(self, user_id: str, revised_plan: RevisedPlan) -> None:
        try:
            self._confirmation_flow.apply_plan(user_id, revised_plan)
            LOGGER.info("Apply recorded for user %s, plan %s", user_id, revised_plan.plan_id)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Apply failed: %s", error)

    @staticmethod
    def _extract_affected(disruption: Dict[str, Any]) -> AffectedElement:
        ae = disruption.get("affected_element", {}) if isinstance(disruption.get("affected_element"), dict) else {}
        return AffectedElement(
            activity_name=str(ae.get("activity_name", "")) or str(disruption.get("activity_name", "")) or "unknown",
            time_slot=str(ae.get("time_slot", "")),
            day=str(ae.get("day", "")),
            location=str(ae.get("location", "")),
        )

    @staticmethod
    def _build_anchor(user_id: str, original_itinerary: Dict[str, Any]) -> IntentAnchor:
        return IntentAnchor(
            user_id=user_id,
            vibe=(original_itinerary.get("vibe") or "relaxed"),
            budget=float(original_itinerary.get("budget_total") or original_itinerary.get("budget") or 0.0),
            confirmed_bookings=list(original_itinerary.get("confirmed_bookings", []) or []),
            must_see=list(original_itinerary.get("must_see", []) or []),
        )

    @staticmethod
    def _alts_to_activities(alts: List[dict], reason: str) -> List[RevisedActivity]:
        activities: List[RevisedActivity] = []
        for alt in alts[:10]:
            if not isinstance(alt, dict):
                continue
            activities.append(
                RevisedActivity(
                    activity_name=str(alt.get("activity_name", alt.get("name", "Alternative"))),
                    time_slot=str(alt.get("time_slot", "")),
                    duration=str(alt.get("duration", "")),
                    reason=reason,
                )
            )
        return activities


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from app.replanning.dynamic_replanning import DynamicReplanner, AffectedElement, IntentAnchor

    disruption = {
        "disruption_id": "d_mock_001",
        "severity": "day",
        "affected_element": {
            "activity_name": "Ella train ride",
            "day": "Day 3",
            "time_slot": "morning",
            "location": "Ella",
        },
    }

    original_itinerary = {
        "plan_id": "orig_plan_001",
        "vibe": "relaxed",
        "budget_total": 1200.0,
        "confirmed_bookings": ["hotel_001"],
        "must_see": ["Sigiriya"],
    }

    replanner = DynamicReplanner()
    revised = replanner.replan(disruption, user_id="demo_user", original_itinerary=original_itinerary)
    print(format_revised_plan(revised))
