"""Multi-turn conversation tracking for the Dynamic Replanning module.

Tracks conversation turns (user message, system response, decision) per
user and persists them via :class:`ReplanningStateManager`. Every
tracked turn is logged for auditability.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.replanning.dynamic_replanning.state_manager import (
    ReplanningStateManager,
)
from app.schemas.replanning import Decision, TurnRecord

LOGGER = logging.getLogger(__name__)


class MultiTurnTracker:
    """Track and retrieve conversation turns across replanning sessions."""

    def __init__(self, state_manager: ReplanningStateManager | None = None):
        """Create a tracker backed by a state manager.

        Args:
            state_manager: State manager to persist turns in. A new
                instance is created when omitted.
        """

        self._state_manager = state_manager or ReplanningStateManager()

        LOGGER.info("MultiTurnTracker initialised")

    def track_turn(
        self,
        user_id: str,
        user_message: str,
        system_response: str,
        decision: str,
    ) -> TurnRecord:
        """Record a new turn and persist it.

        The next turn number is derived from the existing conversation
        history.
        """

        context = self._state_manager.get_conversation_context(user_id)
        turn_number = len(context) + 1

        turn = TurnRecord(
            turn_number=turn_number,
            user_message=user_message or "",
            system_response=system_response or "",
            decision=(decision or "modified") if decision in ("accepted", "rejected", "modified") else "modified",
        )

        self._state_manager.add_turn(user_id, turn)

        LOGGER.info(
            "Tracked turn %d for user %s (decision=%s)",
            turn.turn_number,
            user_id,
            turn.decision,
        )

        return turn

    def get_recent_turns(self, user_id: str, n: int = 5) -> List[TurnRecord]:
        """Return the most recent ``n`` turns for ``user_id``."""

        context = self._state_manager.get_conversation_context(user_id)

        recent = context[-max(1, n) :] if n >= 0 else context
        if recent:
            LOGGER.debug(
                "Returning %d recent turns for user %s (of %d total)",
                len(recent),
                user_id,
                len(context),
            )

        return recent

    def get_all_turns(self, user_id: str) -> List[TurnRecord]:
        """Return all recorded turns for ``user_id``."""

        return self._state_manager.get_conversation_context(user_id)

    def get_preference_history(self, user_id: str) -> Dict[str, List[str]]:
        """Return a lightweight preference history aggregated from turns.

        This is a heuristic summary (decision counts by type). It is
        intended to support cross-turn consistency checks and can be
        extended later.
        """

        context = self._state_manager.get_conversation_context(user_id)

        decisions: List[str] = [turn.decision for turn in context]

        history: Dict[str, List[str]] = {
            "accepted": [d for d in decisions if d == "accepted"],
            "rejected": [d for d in decisions if d == "rejected"],
            "modified": [d for d in decisions if d == "modified"],
            "decision_counts": {
                "accepted": len([d for d in decisions if d == "accepted"]),
                "rejected": len([d for d in decisions if d == "rejected"]),
                "modified": len([d for d in decisions if d == "modified"]),
                "total": len(decisions),
            },
        }

        LOGGER.debug("Preference history for user %s: %s", user_id, history["decision_counts"])

        return history


__all__ = ["MultiTurnTracker"]
