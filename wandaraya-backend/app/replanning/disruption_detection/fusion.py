"""Weighted fusion of disruption signals."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.replanning.disruption_detection.utils import load_config

LOGGER = logging.getLogger(__name__)

#: Intensity -> base weather score.
_RAIN_SCORES = {
    "none": 0.0,
    "light": 0.4,
    "heavy": 0.7,
    "storm": 1.0,
}

#: Heat warning floors the weather score at this value (rain or not).
_HEAT_FLOOR = 0.5

_PLACES_CROWD_SCORES = {"low": 0.0, "medium": 0.3, "high": 0.6}

_SOURCES = ("weather", "places", "complaint", "gps")


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

    def source_score(
        self, signals: Dict[str, Any], source: str
    ) -> float:
        """Public probe of one source's normalised score, used for per-disruption confidence."""
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


__all__ = ["FusionEngine", "fuse"]