"""Cross-turn consistency validation for the Dynamic Replanning module.

Hybrid design (production-first):
1. Hard rules catch obvious contradictions (removed must-see, removed
   confirmed booking, reintroduced rejection) — these are non-negotiable
   safety checks with drift probability 1.0.
2. A Random Forest classifier (``consistency_classifier_rf.pkl``) catches
   subtle intent drift from the 12 PPE-simulated features when the hard
   rules pass.

The classifier is optional at runtime: when the model or its dependencies
are unavailable, the checker degrades gracefully to rules-only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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


def _plan_activity_names(plan: Any) -> List[str]:
    """Return activity names from a dict plan or a ``RevisedPlan``."""

    if isinstance(plan, dict):
        names = []
        for activity in plan.get("activities", []) or []:
            if isinstance(activity, dict):
                names.append(str(activity.get("name", "")))
            else:
                names.append(str(activity))
        return names

    revised = getattr(plan, "revised_activities", None) or []
    names = [str(a.activity_name) for a in revised if getattr(a, "activity_name", None)]
    affected = getattr(plan, "affected_element", None)
    if affected is not None and getattr(affected, "activity_name", None):
        names.append(str(affected.activity_name))
    return names


def _is_full_plan(plan: Any) -> bool:
    """True when ``plan`` is a complete itinerary (dict with activities)."""

    return isinstance(plan, dict) and bool(plan.get("activities"))


def _history_rejections(conversation_history: Optional[List[Any]]) -> List[str]:
    """Extract rejected attraction/alternative names from turn history."""

    rejections: List[str] = []
    for turn in conversation_history or []:
        if isinstance(turn, dict):
            for name in turn.get("rejections", []) or []:
                if name and name not in rejections:
                    rejections.append(str(name))
    return rejections


class CrossTurnConsistency:
    """Validate that a proposed plan is consistent across conversation turns."""

    def __init__(
        self,
        config: Dict | None = None,
        enforce_vibe: bool | None = None,
        enforce_budget: bool | None = None,
        enforce_bookings: bool | None = None,
        enforce_must_see: bool | None = None,
        enable_ml: bool | None = None,
        model_dir: str | None = None,
    ) -> None:
        """Create a hybrid (rules + RF) consistency checker."""

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

        classifier_config = self._config.get("consistency_classifier", {}) or {}

        self._enable_ml = (
            enable_ml
            if enable_ml is not None
            else bool(classifier_config.get("enabled", False))
        )
        self._model_dir = model_dir

        # Lazily initialised so importing this module never requires sklearn.
        self._classifier: Any = None
        self._classifier_checked = False

        LOGGER.info(
            "CrossTurnConsistency initialised (vibe=%s, budget=%s, "
            "bookings=%s, must_see=%s, enable_ml=%s)",
            self._enforce_vibe,
            self._enforce_budget,
            self._enforce_bookings,
            self._enforce_must_see,
            self._enable_ml,
        )

    def check_consistency(
        self,
        user_id: str,
        proposed_plan: RevisedPlan,
        anchor: IntentAnchor,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        features: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyCheck:
        """Hybrid check: hard rules first, then the RF drift classifier."""

        # Step 1 — hard rules (safety, non-negotiable).
        reasons: List[str] = []

        if self._enforce_must_see and anchor.must_see:
            violated = self.prior_constraint_violated(
                proposed_plan, anchor, conversation_history
            )
            if violated:
                reasons.append(
                    "Prior constraint violated: must-see item(s) missing or "
                    f"replaced: {', '.join(violated)}"
                )

        if self._enforce_bookings and anchor.confirmed_bookings:
            removed = self.prior_confirmation_removed(proposed_plan, anchor)
            if removed:
                reasons.append(
                    "Previously confirmed item removed: " + ", ".join(removed)
                )

        reintroduced = self.prior_rejection_reintroduced(
            proposed_plan, anchor, conversation_history
        )
        if reintroduced:
            reasons.append(
                "Previously rejected alternative reintroduced: "
                + ", ".join(reintroduced)
            )

        if reasons:
            check = ConsistencyCheck(
                consistent=False,
                reasons=reasons,
                drift_probability=1.0,
                reason="; ".join(reasons),
            )
            LOGGER.info(
                "Consistency check for user %s, plan %s: hard rule violation "
                "(reasons=%d)",
                user_id,
                getattr(proposed_plan, "plan_id", None)
                or (proposed_plan.get("plan_id") if isinstance(proposed_plan, dict) else "?"),
                len(reasons),
            )
            return check

        # Step 2 — RF classifier catches subtle intent drift.
        ml_result = self._predict_ml(
            user_id, proposed_plan, anchor, conversation_history, features
        )

        if ml_result is None:
            check = ConsistencyCheck(
                consistent=True,
                reasons=[],
                drift_probability=0.0,
                reason="Rules-only consistency check (ML unavailable)",
            )
        else:
            drift_detected = bool(ml_result["drift_detected"])
            probability = float(ml_result["probability"])
            check = ConsistencyCheck(
                consistent=not drift_detected,
                reasons=(
                    []
                    if not drift_detected
                    else [
                        "RF drift classifier flagged intent drift "
                        f"(p={probability:.4f})"
                    ]
                ),
                drift_probability=probability,
                reason="RF-based consistency check",
            )

        LOGGER.info(
            "Consistency check for user %s, plan %s: consistent=%s "
            "(reasons=%d, drift_p=%s)",
            user_id,
            getattr(proposed_plan, "plan_id", None)
            or (proposed_plan.get("plan_id") if isinstance(proposed_plan, dict) else "?"),
            check.consistent,
            len(check.reasons),
            check.drift_probability,
        )

        return check

    # ------------------------------------------------------------------
    # Hard rules
    # ------------------------------------------------------------------

    def prior_constraint_violated(
        self,
        proposed_plan: Any,
        anchor: IntentAnchor,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Return must-see items the proposed plan removes or replaces.

        Full itinerary plans (dicts with ``activities``) are checked for
        missing must-see attractions. Revision-scoped plans (``RevisedPlan``)
        only replace a single element, so a violation is flagged when the
        replacement target itself is a must-see item.
        """

        violations: List[str] = []

        if _is_full_plan(proposed_plan):
            plan_names = set(_plan_activity_names(proposed_plan))
            violations.extend(
                name for name in anchor.must_see if name not in plan_names
            )
            return violations

        # Revision-scoped mode: replacing a must-see activity is a violation.
        replaced_names = set(_plan_activity_names(proposed_plan))
        violations.extend(
            name for name in anchor.must_see if name in replaced_names
        )

        # Vibe constraint (dict plans carry an explicit vibe).
        if (
            self._enforce_vibe
            and isinstance(proposed_plan, dict)
            and proposed_plan.get("vibe")
            and anchor.vibe
            and proposed_plan["vibe"] != anchor.vibe
        ):
            violations.append(f"vibe:{anchor.vibe}->{proposed_plan['vibe']}")

        # Budget constraint (dict plans carry an explicit total cost).
        if (
            self._enforce_budget
            and isinstance(proposed_plan, dict)
            and proposed_plan.get("total_cost_usd") is not None
            and anchor.budget
            and float(proposed_plan["total_cost_usd"]) > float(anchor.budget)
        ):
            violations.append(
                f"budget:{anchor.budget}->{proposed_plan['total_cost_usd']}"
            )

        return violations

    def prior_confirmation_removed(
        self,
        proposed_plan: Any,
        anchor: IntentAnchor,
    ) -> List[str]:
        """Return confirmed bookings the proposed plan drops."""

        plan_bookings: Optional[set] = None
        if isinstance(proposed_plan, dict):
            raw = proposed_plan.get("confirmed_bookings")
            if raw is not None:
                plan_bookings = set(raw)
        else:
            raw = getattr(proposed_plan, "confirmed_bookings", None)
            if raw is not None:
                plan_bookings = set(raw)

        if plan_bookings is not None:
            return sorted(set(anchor.confirmed_bookings) - plan_bookings)

        # Revision-scoped mode: the plan declares which elements it preserves.
        preserved = {
            str(element).lower()
            for element in getattr(proposed_plan, "preserved_elements", None) or []
        }
        if anchor.confirmed_bookings and preserved:
            if not ({"bookings", "confirmed_bookings"} & preserved):
                return sorted(set(anchor.confirmed_bookings))
        return []

    def prior_rejection_reintroduced(
        self,
        proposed_plan: Any,
        anchor: IntentAnchor,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Return previously rejected alternatives present in the new plan."""

        rejections = _history_rejections(conversation_history)
        if not rejections:
            return []
        plan_names = set(_plan_activity_names(proposed_plan))
        return [name for name in rejections if name in plan_names]

    # ------------------------------------------------------------------
    # ML step
    # ------------------------------------------------------------------

    def _predict_ml(
        self,
        user_id: str,
        proposed_plan: Any,
        anchor: IntentAnchor,
        conversation_history: Optional[List[Dict[str, Any]]],
        features: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Run the RF drift classifier, degrading gracefully on failure."""

        if not self._enable_ml:
            return None

        classifier = self._get_classifier()
        if classifier is None:
            return None

        try:
            feature_dict = (
                features
                if features is not None
                else self.build_runtime_features(
                    proposed_plan, anchor, conversation_history
                )
            )
            prediction = classifier.predict(feature_dict)
        except Exception as error:  # noqa: BLE001 - never break replanning
            LOGGER.warning("Consistency classifier prediction failed: %s", error)
            return None

        return {
            "drift_detected": bool(prediction["drift_detected"]),
            "probability": float(prediction["probability"]),
            "model_used": prediction.get("model_used", "random_forest"),
        }

    def _get_classifier(self) -> Any:
        """Lazily load and cache the RF classifier, or return ``None``."""

        if self._classifier_checked:
            return self._classifier

        self._classifier_checked = True
        try:
            from app.replanning.dynamic_replanning.consistency_classifier import (
                ConsistencyClassifier,
            )

            classifier = (
                ConsistencyClassifier(self._model_dir)
                if self._model_dir
                else ConsistencyClassifier()
            )
            classifier.load_model()
            self._classifier = classifier
        except Exception as error:  # noqa: BLE001 - optional dependency
            LOGGER.warning(
                "Consistency classifier unavailable, running rules-only: %s",
                error,
            )
            self._classifier = None

        return self._classifier

    @staticmethod
    def build_runtime_features(
        proposed_plan: Any,
        anchor: IntentAnchor,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build the 12 model features from runtime replanning objects.

        ``RevisedPlan`` objects only describe the revision (one replaced
        element), not the full itinerary, so anchor must-sees and confirmed
        bookings are not treated as constraints against the partial plan.
        Full dict itineraries are mapped directly.
        """

        from app.replanning.dynamic_replanning.classifiers.consistency._feature_extractor import (
            extract_features,
        )

        history = list(conversation_history or [])
        pace = "moderate"
        no_rushing = False
        for turn in history:
            if isinstance(turn, dict):
                stated = turn.get("constraints_stated") or {}
                if stated.get("pace"):
                    pace = str(stated["pace"])
                if stated.get("no_rushing") is not None:
                    no_rushing = bool(stated["no_rushing"])

        full_plan = _is_full_plan(proposed_plan)

        if full_plan:
            pseudo_conversation = {
                "conversation_id": f"runtime_{anchor.user_id}",
                "num_turns": max(1, len(history)),
                "constraints": {
                    "vibe": anchor.vibe,
                    "budget_usd": float(anchor.budget or 0.0),
                    "pace": pace,
                    "must_see": list(anchor.must_see or []),
                    "no_rushing": no_rushing,
                },
                "confirmations": list(anchor.confirmed_bookings or []),
                "rejections": _history_rejections(history),
                "initial_plan": history[0].get("initial_plan")
                if history and isinstance(history[0], dict) and history[0].get("initial_plan")
                else {"activities": []},
            }
            pseudo_plan = proposed_plan
        else:
            pseudo_conversation = {
                "conversation_id": f"runtime_{anchor.user_id}",
                "num_turns": max(1, len(history)),
                "constraints": {
                    "vibe": anchor.vibe,
                    "budget_usd": float(anchor.budget or 0.0),
                    "pace": pace,
                    "must_see": [],
                    "no_rushing": no_rushing,
                },
                "confirmations": [],
                "rejections": _history_rejections(history),
                "initial_plan": {"activities": []},
            }
            revised_activities = getattr(proposed_plan, "revised_activities", None) or []
            pseudo_plan = {
                "plan_id": getattr(proposed_plan, "plan_id", "runtime_plan"),
                "vibe": None,
                "total_cost_usd": None,
                "activities": [
                    {
                        "attraction_id": index,
                        "name": str(activity.activity_name),
                        "day": 1,
                        "start_minutes": 0,
                        "duration_minutes": 120,
                    }
                    for index, activity in enumerate(revised_activities)
                ],
            }

        return extract_features(pseudo_conversation, pseudo_plan)

    # ------------------------------------------------------------------
    # Existing helpers
    # ------------------------------------------------------------------

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

        if check.reason:
            return check.reason

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
