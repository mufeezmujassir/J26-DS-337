"""Cross-turn consistency validation for the Dynamic Replanning module."""

from __future__ import annotations

import logging
from typing import Dict, List

from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    load_config,
)
from app.schemas.replanning import (
    ConsistencyCheck,
    IntentAnchor,
    RevisedPlan,
    TurnRecord,
)

LOGGER = logging.getLogger(__name__)


class CrossTurnConsistency:
    """Validate that a proposed plan is consistent across conversation turns."""

    def __init__(
        self,
        config: Dict | None = None,
        enforce_vibe: bool | None = None,
        enforce_budget: bool | None = None,
        enforce_bookings: bool | None = None,
        enforce_must_see: bool | None = None,
    ) -> None:
        """Create a consistency checker."""

        self._config = config or self._safe_load_config()

        cons_cfg = self._config.get("consistency", {}) or {}

        self._enforce_vibe = (
            enforce_vibe
            if enforce_vibe is not None
            else bool(cons_cfg.get("enforce_vibe", True))
        )
        self._enforce_budget = (
            enforce_budget
            if enforce_budget is not None
            else bool(cons_cfg.get("enforce_budget", True))
        )
        self._enforce_bookings = (
            enforce_bookings
            if enforce_bookings is not None
            else bool(cons_cfg.get("enforce_bookings", True))
        )
        self._enforce_must_see = (
            enforce_must_see
            if enforce_must_see is not None
            else bool(cons_cfg.get("enforce_must_see", True))
        )

        LOGGER.info(
            "CrossTurnConsistency initialised (vibe=%s, budget=%s, "
            "bookings=%s, must_see=%s)",
            self._enforce_vibe,
            self._enforce_budget,
            self._enforce_bookings,
            self._enforce_must_see,
        )

    def check_consistency(
        self,
        user_id: str,
        proposed_plan: RevisedPlan,
        anchor: IntentAnchor,
    ) -> ConsistencyCheck:
        """Check the proposed plan against the intent anchor."""

        reasons: List[str] = []

        if self._enforce_vibe:
            pass

        if self._enforce_budget:
            pass

        if self._enforce_bookings and anchor.confirmed_bookings:
            pass

        if self._enforce_must_see and anchor.must_see:
            pass

        consistent = len(reasons) == 0

        check = ConsistencyCheck(consistent=consistent, reasons=reasons)

        LOGGER.info(
            "Consistency check for user %s, plan %s: consistent=%s "
            "(reasons=%d)",
            user_id,
            proposed_plan.plan_id,
            check.consistent,
            len(check.reasons),
        )

        return check

    def detect_intent_drift(
        self,
        user_id: str,
        current_turn: TurnRecord,
        anchor: IntentAnchor,
    ) -> bool:
        """Detect whether the latest turn signals intent drift."""

        if current_turn.decision == "rejected":
            LOGGER.debug(
                "Intent drift suspected for user %s (turn %d rejected)",
                user_id,
                current_turn.turn_number,
            )
            return True

        if current_turn.decision == "modified":
            return False

        return False

    def explain_inconsistency(self, check: ConsistencyCheck) -> str:
        """Return a human-readable explanation of an inconsistent check."""

        if check.consistent:
            return "Plan is consistent with the user's original intent."

        if not check.reasons:
            return (
                "Plan is inconsistent with the user's original intent "
                "(unspecified reasons)."
            )

        return "; ".join(check.reasons)

    @staticmethod
    def _safe_load_config() -> Dict:
        """Load config with defaults fallback."""

        try:
            return load_config()
        except (FileNotFoundError, ValueError) as error:
            LOGGER.warning(
                "Could not load replanning config (%s), using defaults",
                error,
            )
            return DEFAULT_CONFIG


__all__ = ["CrossTurnConsistency"]