"""Confirmation flow for the Dynamic Replanning module."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.replanning.dynamic_replanning.state_manager import (
    ReplanningStateManager,
)
from app.schemas.replanning import ConfirmationResult, RevisedPlan

LOGGER = logging.getLogger(__name__)


class ConfirmationFlow:
    """Handle presenting a revised plan and capturing user confirmation."""

    def __init__(self, state_manager: ReplanningStateManager | None = None):
        """Create a confirmation flow."""

        self._state_manager = state_manager or ReplanningStateManager()
        self._last_presented: Dict[str, RevisedPlan] = {}
        self._results: Dict[str, ConfirmationResult] = {}

        LOGGER.info("ConfirmationFlow initialised")

    def present(
        self,
        user_id: str,
        revised_plan: RevisedPlan,
        preserved: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Present the revised plan summary to the user."""

        self._last_presented[user_id] = revised_plan

        affected = revised_plan.affected_element

        disruption_summary = (
            f"Disruption affecting {affected.activity_name or 'activity'}"
        )
        if affected.day:
            disruption_summary += f" (day: {affected.day})"
        if affected.time_slot:
            disruption_summary += f" (time: {affected.time_slot})"
        if affected.location:
            disruption_summary += f" (location: {affected.location})"

        revised_activities = revised_plan.revised_activities
        revised_plan_summary = (
            f"Proposing {len(revised_activities)} revised activity(ies)"
        )

        if revised_activities:
            first = revised_activities[0]
            revised_plan_summary += f": {first.activity_name}"
            if first.time_slot:
                revised_plan_summary += f" [{first.time_slot}]"

        presentation: Dict[str, Any] = {
            "disruption_summary": disruption_summary,
            "revised_plan_summary": revised_plan_summary,
            "preserved_elements": preserved.get("preserved_elements", [])
            if isinstance(preserved, dict)
            else [],
            "requires_confirmation": True,
        }

        LOGGER.info(
            "Presented revised plan %s to user %s (requires_confirmation=%s)",
            revised_plan.plan_id,
            user_id,
            presentation["requires_confirmation"],
        )

        return presentation

    def get_user_confirmation(self, user_id: str) -> ConfirmationResult:
        """Return the stored confirmation result for ``user_id``."""

        result = self._results.get(user_id)

        if result is not None:
            LOGGER.info(
                "Returning stored confirmation for user %s: accepted=%s "
                "next=%s",
                user_id,
                result.accepted,
                result.next_action,
            )
            return result

        plan = self._last_presented.get(user_id) or (
            self._state_manager.get_current_plan(user_id)
        )

        default = ConfirmationResult(
            accepted=False,
            user_feedback="No confirmation received",
            next_action="find_alternative",
        )

        if plan is not None:
            LOGGER.debug(
                "No stored confirmation for user %s; returning default",
                user_id,
            )

        return default

    def request_alternative(self, user_id: str) -> None:
        """Record that the user wants another alternative found."""

        result = ConfirmationResult(
            accepted=False,
            user_feedback="User requested alternative",
            next_action="find_alternative",
        )

        self._results[user_id] = result

        LOGGER.info("User %s requested alternative", user_id)

    def apply_plan(self, user_id: str, revised_plan: RevisedPlan) -> None:
        """Record that the user accepted the plan and it should be applied."""

        result = ConfirmationResult(
            accepted=True,
            user_feedback="User accepted revised plan",
            next_action="apply",
        )

        self._results[user_id] = result

        LOGGER.info(
            "User %s accepted plan %s; apply_plan recorded",
            user_id,
            revised_plan.plan_id,
        )


__all__ = ["ConfirmationFlow"]