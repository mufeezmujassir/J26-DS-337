"""Intent preservation for the Dynamic Replanning module."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    load_config,
    now_utc,
)
from app.schemas.replanning import IntentAnchor, RevisedPlan

LOGGER = logging.getLogger(__name__)

# Hybrid decision vocabulary.
DECISION_PRESERVED = "preserved"
DECISION_BROKEN = "broken"
DECISION_UNCERTAIN = "uncertain"

# Fusion thresholds (mirrors the disruption-detection fusion engine).
DEFAULT_CONFIRM_THRESHOLD = 0.7
DEFAULT_NO_PRESERVE_THRESHOLD = 0.4

MODEL_USED_RF = "random_forest"
MODEL_USED_NONE = "rules_only"


def fuse_intent_decision(
    rule_preserved: bool,
    ml_block: Optional[Dict[str, Any]],
    confirm_threshold: float = DEFAULT_CONFIRM_THRESHOLD,
    no_preserve_threshold: float = DEFAULT_NO_PRESERVE_THRESHOLD,
) -> Dict[str, Any]:
    """Fuse a hard-rule verdict with an ML prediction into one decision."""

    if ml_block is None:
        decision = DECISION_PRESERVED if rule_preserved else DECISION_BROKEN
        return {
            "decision": decision,
            "requires_confirmation": not rule_preserved,
            "model_used": MODEL_USED_NONE,
            "ml_probability": None,
            "ml_preserved": None,
            "detected_by": {
                "rules": not rule_preserved,
                "ml_classifier": False,
            },
        }

    probability = float(ml_block["probability"])
    ml_preserved = bool(ml_block["preserved"])
    ml_strong = probability >= confirm_threshold
    ml_weak = probability < no_preserve_threshold

    if rule_preserved and ml_preserved:
        decision = DECISION_PRESERVED
        requires_confirmation = False
    elif not rule_preserved:
        # Hard rules are non-negotiable: any rule break wins.
        decision = DECISION_BROKEN
        requires_confirmation = True
    elif ml_weak:
        decision = DECISION_BROKEN
        requires_confirmation = True
    elif ml_strong:
        decision = DECISION_PRESERVED
        requires_confirmation = False
    else:
        decision = DECISION_UNCERTAIN
        requires_confirmation = True

    return {
        "decision": decision,
        "requires_confirmation": requires_confirmation,
        "model_used": MODEL_USED_RF,
        "ml_probability": round(probability, 4),
        "ml_preserved": ml_preserved,
        "detected_by": {
            "rules": not rule_preserved,
            "ml_classifier": ml_preserved or ml_weak,
        },
    }


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Best-effort float conversion, returning ``default`` on failure."""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _activity_name(item: Any) -> str:
    """Return a stable name for a runtime activity-like object."""

    if isinstance(item, dict):
        return str(item.get("name") or item.get("activity_name") or "")
    return str(getattr(item, "activity_name", "") or getattr(item, "name", ""))


class IntentPreserver:
    """Validate that a proposed revision preserves the user's intent."""

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        strict_vibe: bool | None = None,
        strict_budget: bool | None = None,
        strict_bookings: bool | None = None,
        enable_ml: bool | None = None,
        model_dir: str | None = None,
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

        classifier_config = self._config.get("intent_classifier", {}) or {}
        hybrid_config = classifier_config.get("hybrid", {}) or {}

        self._enable_ml = (
            enable_ml
            if enable_ml is not None
            else bool(classifier_config.get("enabled", False))
        )
        self._model_dir = model_dir
        self._decision_threshold = float(
            classifier_config.get("decision_threshold", 0.5)
        )
        self._confirm_threshold = float(
            hybrid_config.get("confirm_threshold", DEFAULT_CONFIRM_THRESHOLD)
        )
        self._no_preserve_threshold = float(
            hybrid_config.get(
                "no_preserve_threshold", DEFAULT_NO_PRESERVE_THRESHOLD
            )
        )

        # Lazily initialised so importing this module never requires sklearn.
        self._classifier: Any = None
        self._classifier_checked = False

        LOGGER.info(
            "IntentPreserver initialised (strict_vibe=%s, "
            "strict_budget=%s, strict_bookings=%s, enable_ml=%s)",
            self._strict_vibe,
            self._strict_budget,
            self._strict_bookings,
            self._enable_ml,
        )

    def preserve(
        self,
        original_itinerary: Dict[str, Any],
        revised_plan: RevisedPlan,
        anchor: IntentAnchor,
        features: Dict[str, Any] | None = None,
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
            "rule_based_preserved": is_preserved,
            "model_used": MODEL_USED_NONE,
        }

        ml_block = self._predict_ml(
            original_itinerary, revised_plan, anchor, features
        )
        hybrid_block = self._fuse_hybrid(is_preserved, ml_block)

        report["ml"] = ml_block
        report["hybrid"] = hybrid_block
        if ml_block is not None:
            report["model_used"] = MODEL_USED_RF
            if hybrid_block["decision"] == DECISION_UNCERTAIN:
                report["recommendation"] = (
                    "Review before confirmation: hard rules pass but the "
                    "learned intent classifier flags possible intent drift."
                )

        LOGGER.info(
            "Preservation check complete for plan %s: preserved=%s "
            "broken=%s decision=%s ml_p=%s",
            revised_plan.plan_id,
            preserved,
            broken,
            hybrid_block["decision"],
            ml_block["probability"] if ml_block else None,
        )

        return report

    def predict_intent(
        self,
        original_itinerary: Dict[str, Any],
        revised_plan: RevisedPlan,
        anchor: IntentAnchor,
        features: Dict[str, Any] | None = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the raw ML prediction, or ``None`` if unavailable."""

        return self._predict_ml(
            original_itinerary, revised_plan, anchor, features
        )

    def _predict_ml(
        self,
        original_itinerary: Dict[str, Any],
        revised_plan: RevisedPlan,
        anchor: IntentAnchor,
        features: Dict[str, Any] | None,
    ) -> Optional[Dict[str, Any]]:
        """Run the intent classifier, degrading gracefully on any failure."""

        if not self._enable_ml:
            return None

        classifier = self._get_classifier()
        if classifier is None:
            return None

        try:
            feature_dict = (
                features
                if features is not None
                else self.build_features(original_itinerary, revised_plan, anchor)
            )
            prediction = classifier.predict(feature_dict)
        except Exception as error:  # noqa: BLE001 - never break replanning
            LOGGER.warning("Intent classifier prediction failed: %s", error)
            return None

        return {
            "probability": prediction["probability"],
            "preserved": bool(prediction["intent_preserved"]),
            "model_used": prediction.get("model_used", MODEL_USED_RF),
        }

    def _fuse_hybrid(
        self, rule_preserved: bool, ml_block: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Combine the hard-rule verdict with the ML probability."""

        return fuse_intent_decision(
            rule_preserved,
            ml_block,
            confirm_threshold=self._confirm_threshold,
            no_preserve_threshold=self._no_preserve_threshold,
        )

    def _get_classifier(self) -> Any:
        """Lazily load and cache the ML classifier, or return ``None``."""

        if self._classifier_checked:
            return self._classifier

        self._classifier_checked = True
        try:
            from app.replanning.dynamic_replanning.intent_classifier import (
                IntentClassifier,
            )

            classifier = (
                IntentClassifier(self._model_dir)
                if self._model_dir
                else IntentClassifier()
            )
            classifier.load_model()
            self._classifier = classifier
        except Exception as error:  # noqa: BLE001 - optional dependency
            LOGGER.warning(
                "Intent classifier unavailable, running rules-only: %s", error
            )
            self._classifier = None

        return self._classifier

    @staticmethod
    def build_features(
        original_itinerary: Dict[str, Any],
        revised_plan: RevisedPlan,
        anchor: IntentAnchor,
    ) -> Dict[str, Any]:
        """Build the 14 model features from runtime replanning objects."""

        original = original_itinerary or {}
        context = original.get("context", {}) or {}

        orig_vibe = original.get("vibe")
        anchor_vibe = anchor.vibe
        vibe_match = int(orig_vibe == anchor_vibe) if orig_vibe is not None else 1

        orig_total = _to_float(
            original.get("budget_total", original.get("budget"))
        )
        anchor_budget = _to_float(anchor.budget, 0.0) or 0.0
        if orig_total is not None and anchor_budget > 0.0:
            budget_diff_ratio = max(
                0.0, (orig_total - anchor_budget) / anchor_budget
            )
        else:
            budget_diff_ratio = 0.0

        orig_bookings = set(original.get("confirmed_bookings", []) or [])
        anchor_bookings = set(anchor.confirmed_bookings or [])
        bookings_preserved_ratio = (
            len(orig_bookings & anchor_bookings) / len(orig_bookings)
            if orig_bookings
            else 1.0
        )

        orig_must_see = set(original.get("must_see", []) or [])
        anchor_must_see = set(anchor.must_see or [])
        must_see_preserved_ratio = (
            len(orig_must_see & anchor_must_see) / len(orig_must_see)
            if orig_must_see
            else 1.0
        )

        orig_activities = [
            a for a in (original.get("activities", []) or [])
            if _activity_name(a)
        ]
        revised_activities = list(
            getattr(revised_plan, "revised_activities", []) or []
        )

        orig_names = {_activity_name(a) for a in orig_activities}
        revised_names = [_activity_name(a) for a in revised_activities if _activity_name(a)]
        num_activities_changed = sum(
            1 for name in revised_names if name not in orig_names
        )
        activity_count_change = len(revised_names) - len(orig_activities)
        ratio_activities_changed = (
            num_activities_changed / len(orig_activities)
            if orig_activities
            else 0.0
        )

        anchor_created = getattr(anchor, "created_at", None)
        if anchor_created is not None:
            if anchor_created.tzinfo is None:
                anchor_created = anchor_created.replace(tzinfo=timezone.utc)
            anchor_age_minutes = max(
                0, int((now_utc() - anchor_created).total_seconds() // 60)
            )
        else:
            anchor_age_minutes = 0

        return {
            "vibe_match": vibe_match,
            "budget_diff_ratio": float(budget_diff_ratio),
            "bookings_preserved_ratio": float(bookings_preserved_ratio),
            "must_see_preserved_ratio": float(must_see_preserved_ratio),
            "time_shift_minutes": float(
                _to_float(context.get("time_shift_minutes"), 0.0)
            ),
            "activity_count_change": int(activity_count_change),
            "location_distance_km": float(
                _to_float(context.get("location_distance_km"), 0.0)
            ),
            "num_activities_changed": int(num_activities_changed),
            "ratio_activities_changed": float(ratio_activities_changed),
            "anchor_age_minutes": int(
                context.get("anchor_age_minutes", anchor_age_minutes)
            ),
            "num_turns_since_anchor": int(
                context.get("num_turns_since_anchor", 0)
            ),
            "user_explicitly_changed_vibe": int(
                context.get("user_explicitly_changed_vibe", 0)
            ),
            "user_explicitly_changed_budget": int(
                context.get("user_explicitly_changed_budget", 0)
            ),
            "num_prior_replans": int(context.get("num_prior_replans", 0)),
        }

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


__all__ = [
    "IntentPreserver",
    "fuse_intent_decision",
    "DECISION_PRESERVED",
    "DECISION_BROKEN",
    "DECISION_UNCERTAIN",
]