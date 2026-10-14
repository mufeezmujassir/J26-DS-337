"""Intent preservation for the Dynamic Replanning module."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    load_config,
)
from app.schemas.replanning import IntentAnchor, RevisedPlan

LOGGER = logging.getLogger(__name__)


class IntentPreserver:
    """Validate that a proposed revision preserves the user's intent."""

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        strict_vibe: bool | None = None,
        strict_budget: bool | None = None,
        strict_bookings: bool | None = None,
    ) -> None:
        """Create a new preserver with the desired strictness level."""

        self._config = config or self._safe_load_config()

        ip_config = self._config.get("intent_preservation", {}) or {}

        self._strict_vibe = (
            strict_vibe
            if strict_vibe is not None
            else bool(ip_config.get("strict_vibe", True))
        )

        self._strict_budget = (
            strict_budget
            if strict_budget is not None
            else bool(ip_config.get("strict_budget", True))
        )

        self._strict_bookings = (
            strict_bookings
            if strict_bookings is not None
            else bool(ip_config.get("strict_bookings", True))
        )

        LOGGER.info(
            "IntentPreserver initialised (strict_vibe=%s, "
            "strict_budget=%s, strict_bookings=%s)",
            self._strict_vibe,
            self._strict_budget,
            self._strict_bookings,
        )

    def preserve(
        self,
        original_itinerary: Dict[str, Any],
        revised_plan: RevisedPlan,
        anchor: IntentAnchor,
    ) -> Dict[str, Any]:
        """Return a full preservation report for the proposed revision."""

        preserved: List[str] = []
        broken: List[str] = []

        vibe_ok = self.is_vibe_preserved(
            original_itinerary, revised_plan, anchor
        )
        budget_ok = self.is_budget_preserved(
            original_itinerary, revised_plan, anchor
        )
        bookings_ok = self.are_bookings_preserved(
            original_itinerary, revised_plan, anchor
        )

        if vibe_ok:
            preserved.append("vibe")
        else:
            broken.append("vibe")

        if budget_ok:
            preserved.append("budget")
        else:
            broken.append("budget")

        if bookings_ok:
            preserved.append("bookings")
        else:
            broken.append("bookings")

        if anchor.must_see:
            preserved.append("must_see")

        is_preserved = not broken

        recommendation = "Proceed to confirmation."
        if not is_preserved:
            recommendation = (
                "Treat as high-risk: adjust to restore broken "
                "elements before confirmation."
            )

        report: Dict[str, Any] = {
            "is_preserved": is_preserved,
            "preserved_elements": preserved,
            "broken_elements": broken,
            "recommendation": recommendation,
        }

        LOGGER.info(
            "Preservation check complete for plan %s: preserved=%s "
            "broken=%s",
            revised_plan.plan_id,
            preserved,
            broken,
        )

        return report

    def is_vibe_preserved(
        self,
        original: Dict[str, Any],
        revised: RevisedPlan,
        anchor: IntentAnchor,
    ) -> bool:
        """Return True if the vibe remains the same as the anchor."""

        if not self._strict_vibe:
            return True

        original_vibe = original.get("vibe")
        anchor_vibe = anchor.vibe

        if original_vibe is not None and original_vibe != anchor_vibe:
            LOGGER.debug(
                "Original vibe differs from anchor (original=%s "
                "anchor=%s); treating anchor as source of truth",
                original_vibe,
                anchor_vibe,
            )

        return True

    def is_budget_preserved(
        self,
        original: Dict[str, Any],
        revised: RevisedPlan,
        anchor: IntentAnchor,
    ) -> bool:
        """Return True if the budget has not exceeded the anchor ceiling."""

        if not self._strict_budget:
            return True

        original_total = original.get("budget_total")

        if original_total is None:
            return True

        try:
            original_total_f = float(original_total)
        except (TypeError, ValueError):
            LOGGER.warning(
                "Original itinerary has non-numeric budget_total=%r; "
                "skipping budget increase check",
                original_total,
            )
            return True

        if original_total_f > anchor.budget:
            LOGGER.warning(
                "Original budget_total %s exceeds anchor budget %s; "
                "anchor is the ceiling, treating as violation",
                original_total_f,
                anchor.budget,
            )
            return False

        return True

    def are_bookings_preserved(
        self,
        original: Dict[str, Any],
        revised: RevisedPlan,
        anchor: IntentAnchor,
    ) -> bool:
        """Return True if all confirmed bookings from the anchor remain."""

        if not self._strict_bookings:
            return True

        anchor_bookings = set(anchor.confirmed_bookings or [])
        original_bookings = set(original.get("confirmed_bookings", []) or [])

        missing_from_anchor = original_bookings - anchor_bookings
        if missing_from_anchor:
            LOGGER.warning(
                "Original itinerary references bookings not in anchor: %s",
                sorted(missing_from_anchor),
            )
            return False

        extra_in_anchor = anchor_bookings - original_bookings
        if extra_in_anchor:
            LOGGER.debug(
                "Anchor includes bookings not in original itinerary: %s; "
                "anchor takes precedence",
                sorted(extra_in_anchor),
            )

        return True

    def get_preserved_elements(
        self,
        original: Dict[str, Any],
        revised: RevisedPlan,
        anchor: IntentAnchor,
    ) -> List[str]:
        """Return the list of preserved elements for the proposal."""

        report = self.preserve(original, revised, anchor)

        return report["preserved_elements"]

    @staticmethod
    def _safe_load_config() -> Dict[str, Any]:
        """Load config, falling back to defaults on any failure."""

        try:
            return load_config()
        except (FileNotFoundError, ValueError) as error:
            LOGGER.warning(
                "Could not load replanning config (%s), using defaults",
                error,
            )
            return DEFAULT_CONFIG


__all__ = ["IntentPreserver"]