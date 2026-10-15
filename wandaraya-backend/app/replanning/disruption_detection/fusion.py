"""Weighted fusion of disruption signals."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.replanning.disruption_detection.severity_classifier import (
    classify_severity,
    rank as severity_rank,
)
from app.replanning.disruption_detection.utils import load_config

LOGGER = logging.getLogger(__name__)

# Intensity -> base weather score.
_RAIN_SCORES = {
    "none": 0.0,
    "light": 0.4,
    "heavy": 0.7,
    "storm": 1.0,
}

# Heat warning floors the weather score at this value (rain or not).
_HEAT_FLOOR = 0.5

_PLACES_CROWD_SCORES = {"low": 0.0, "medium": 0.3, "high": 0.6}

_SOURCES = ("weather", "places", "complaint", "gps")

# ML probability at/above which a disruption is considered strong.
DEFAULT_CONFIRM_THRESHOLD = 0.7

# ML probability below which (with no firing rule) there is no disruption.
DEFAULT_NO_DISRUPTION_THRESHOLD = 0.4

# Hybrid decision vocabulary.
DECISION_CONFIRMED = "confirmed"
DECISION_NEEDS_CONFIRMATION = "needs_confirmation"
DECISION_NONE = "none"
DECISION_UNCERTAIN = "uncertain"

# Severity used when no disruption is present.
SEVERITY_NONE = "none"


def _highest_severity(*levels: str) -> str:
    """Return the strongest severity among ``levels`` (ties keep the first)."""
    resolved = [level or SEVERITY_NONE for level in levels]
    return max(resolved, key=severity_rank)


class FusionEngine:
    """Combines per-source signals into a single disruption score."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or load_config("config.yaml")
        fusion_config = self.config.get("fusion", {})
        self.weights: Dict[str, float] = fusion_config.get(
            "weights",
            {"weather": 0.30, "places": 0.30, "complaint": 0.25, "gps": 0.15},
        )
        self.confirmation_threshold: float = fusion_config.get(
            "confirmation_threshold", 0.75
        )
        hybrid_config = self.config.get("hybrid", {})
        self.confirm_threshold: float = hybrid_config.get(
            "confirm_threshold", DEFAULT_CONFIRM_THRESHOLD
        )
        self.no_disruption_threshold: float = hybrid_config.get(
            "no_disruption_threshold", DEFAULT_NO_DISRUPTION_THRESHOLD
        )

    def fuse(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the fused disruption score from the merged signals."""
        source_scores = {
            source: self._source_score(signals, source)
            for source in _SOURCES
        }

        score = round(
            sum(
                self.weights.get(source, 0.0) * source_scores[source]
                for source in _SOURCES
            ),
            3,
        )
        score = max(0.0, min(1.0, score))

        contributing = [
            source for source in _SOURCES if source_scores[source] > 0.0
        ]
        requires_confirmation = score < self.confirmation_threshold

        LOGGER.info(
            "Fusion: score=%.3f sources=%r requires_confirmation=%s",
            score,
            contributing,
            requires_confirmation,
        )

        return {
            "score": score,
            "requires_confirmation": requires_confirmation,
            "contributing_sources": contributing,
        }

    def fuse_hybrid(
        self,
        candidates: List[Dict[str, Any]],
        ml_prediction: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Combine rule-based triggers with an ML prediction.

        Args:
            candidates: rule triggers from :func:`trigger_rules.apply_rules`.
            ml_prediction: output of :meth:`MLClassifier.predict` (or
                ``None`` to run in rules-only mode).

        Returns:
            A decision mapping with ``decision``, ``is_disruption``,
            ``requires_confirmation``, the effective ``severity`` and a
            ``detected_by`` provenance block.
        """
        rule_fired = bool(candidates)
        ml_probability = 0.0
        ml_severity = SEVERITY_NONE
        ml_is_disruption = False

        if ml_prediction:
            ml_probability = float(
                ml_prediction.get("probability", 0.0) or 0.0
            )
            ml_is_disruption = bool(
                ml_prediction.get("is_disruption", False)
            )
            ml_severity = str(
                ml_prediction.get(
                    "ml_severity", ml_prediction.get("severity", SEVERITY_NONE)
                )
            )

        rule_severity = classify_severity(candidates)

        if rule_fired and ml_probability >= self.confirm_threshold:
            decision = DECISION_CONFIRMED
            is_disruption = True
            requires_confirmation = False
        elif rule_fired or ml_probability >= self.confirm_threshold:
            decision = DECISION_NEEDS_CONFIRMATION
            is_disruption = True
            requires_confirmation = True
        elif ml_probability < self.no_disruption_threshold:
            decision = DECISION_NONE
            is_disruption = False
            requires_confirmation = False
        else:
            decision = DECISION_UNCERTAIN
            is_disruption = False
            requires_confirmation = True

        # Highest severity across the rule engine and the ML severity model.
        severity = _highest_severity(rule_severity, ml_severity)
        if not is_disruption:
            LOGGER.info(
                "Hybrid fusion: decision=%s (rule_fired=%s, p=%.3f) "
                "logged only",
                decision,
                rule_fired,
                ml_probability,
            )
            effective_severity = SEVERITY_NONE
        else:
            effective_severity = severity

        detected_by = {
            "rules": [rule.get("name", "") for rule in candidates],
            "ml_classifier": bool(ml_prediction)
            and (ml_is_disruption or ml_probability >= self.confirm_threshold),
            "ml_severity": ml_severity,
        }

        LOGGER.info(
            "Hybrid fusion: decision=%s rule_fired=%s ml_p=%.3f "
            "severity=%s requires_confirmation=%s",
            decision,
            rule_fired,
            ml_probability,
            effective_severity,
            requires_confirmation,
        )

        return {
            "decision": decision,
            "is_disruption": is_disruption,
            "requires_confirmation": requires_confirmation,
            "severity": effective_severity,
            "rule_severity": rule_severity,
            "ml_severity": ml_severity,
            "ml_probability": round(ml_probability, 4),
            "detected_by": detected_by,
        }

    def source_score(
        self, signals: Dict[str, Any], source: str
    ) -> float:
        """Public probe of one source's normalised score."""
        return self._source_score(signals, source)

    def _source_score(
        self, signals: Dict[str, Any], source: str
    ) -> float:
        """Normalise one source's signal into a [0.0, 1.0] score."""
        section = (
            signals.get(source) if isinstance(signals, dict) else None
        ) or {}
        if not isinstance(section, dict):
            section = {}

        if source == "weather":
            return self._weather_score(section)
        if source == "places":
            return self._places_score(section)
        if source == "complaint":
            return self._complaint_score(section)
        if source == "gps":
            return self._gps_score(section)
        return 0.0

    @staticmethod
    def _weather_score(section: Dict[str, Any]) -> float:
        """Rain intensity + heat heuristic for the weather signal."""
        intensity = section.get("rain_intensity", "none")
        score = _RAIN_SCORES.get(intensity, 0.0)
        if section.get("heat_warning", False) is True:
            score = max(score, _HEAT_FLOOR)
        return round(score, 3)

    @staticmethod
    def _places_score(section: Dict[str, Any]) -> float:
        """Closed attractions dominate; crowd level supplements."""
        if section.get("is_open", True) is False:
            return 1.0
        if section.get("capacity_issue", False) is True:
            return _PLACES_CROWD_SCORES["high"]
        crowd = section.get("crowd_level", "low")
        return _PLACES_CROWD_SCORES.get(crowd, 0.0)

    @staticmethod
    def _complaint_score(section: Dict[str, Any]) -> float:
        """Complaint score is already a normalised 0-1 value."""
        raw = float(section.get("complaint_score", 0.0) or 0.0)
        return max(0.0, min(1.0, raw))

    @staticmethod
    def _gps_score(section: Dict[str, Any]) -> float:
        """Maximum of normalised deviation and schedule delay."""
        deviation_threshold = 5.0
        delay_threshold = 60.0

        deviation = float(section.get("gps_deviation_km", 0.0) or 0.0)
        delay = int(section.get("time_delay_minutes", 0) or 0)

        deviation_component = min(1.0, deviation / deviation_threshold)
        delay_component = min(1.0, delay / delay_threshold)

        return round(max(deviation_component, delay_component), 3)


def fuse(signals: Dict[str, Any], config: Optional[dict] = None) -> Dict[str, Any]:
    """Convenience wrapper around FusionEngine."""
    return FusionEngine(config).fuse(signals)


def fuse_hybrid(
    candidates: List[Dict[str, Any]],
    ml_prediction: Optional[Dict[str, Any]] = None,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """Convenience wrapper around :meth:`FusionEngine.fuse_hybrid`."""
    return FusionEngine(config).fuse_hybrid(candidates, ml_prediction)


__all__ = [
    "FusionEngine",
    "fuse",
    "fuse_hybrid",
    "DECISION_CONFIRMED",
    "DECISION_NEEDS_CONFIRMATION",
    "DECISION_NONE",
    "DECISION_UNCERTAIN",
]