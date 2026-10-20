"""Rule-based labelling (with injected noise) for built datasets.

The labeller mirrors the deterministic bootstrap rules used by the rule engine
so the supervised target is always consistent with the signals the detector
observes at inference time.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Sequence, Tuple

from app.replanning.disruption_detection.classifiers import (
    LABEL_DISRUPTION,
    LABEL_NORMAL,
    SEVERITY_LEVELS,
    SEVERITY_NONE,
)

LOGGER = logging.getLogger(__name__)

# Severity ranking (weakest to strongest) used when several rules match.
_SEVERITY_RANK: Dict[str, int] = {
    SEVERITY_NONE: 0,
    "step": 1,
    "day": 2,
    "plan": 3,
}


class DisruptionLabeler:
    """Derive ``(label, severity)`` pairs and optionally corrupt them.

    Parameters
    ----------
    noise_rate:
        Fraction of rows whose label is deliberately flipped.
    seed:
        Base seed for the deterministic noise injection.
    """

    def __init__(self, noise_rate: float = 0.05, seed: int = 42) -> None:
        if not 0.0 <= noise_rate <= 1.0:
            raise ValueError("noise_rate must be within [0, 1]")
        self.noise_rate = float(noise_rate)
        self.seed = int(seed)

    def label(self, features: Dict[str, Any]) -> Tuple[str, str]:
        """Return the rule-derived ``(label, severity)`` for a feature vector."""
        severity = SEVERITY_NONE

        rain_duration = float(features.get("rain_duration_hours", 0.0))
        is_outdoor = int(features.get("is_outdoor_activity", 0))
        closure_flag = int(features.get("closure_flag", 0))
        capacity_issue = int(features.get("capacity_issue", 0))
        crowd_level = float(features.get("crowd_level_score", 0.0))
        heat_warning = int(features.get("heat_warning", 0))
        complaint_score = float(features.get("complaint_score", 0.0))
        change_request = int(features.get("change_request", 0))
        gps_deviation = float(features.get("gps_deviation_km", 0.0))
        delay = int(features.get("time_delay_minutes", 0))
        num_affected = int(features.get("num_affected_activities", 0))

        def escalate(level: str) -> None:
            nonlocal severity
            if _SEVERITY_RANK[level] > _SEVERITY_RANK[severity]:
                severity = level

        if rain_duration > 3 and is_outdoor == 1:
            escalate("step")
        if closure_flag == 1:
            escalate("step")
        if capacity_issue == 1 and crowd_level > 0.6:
            escalate("step")
        if heat_warning == 1 and is_outdoor == 1:
            escalate("step")
        if complaint_score > 0.7:
            escalate("step")
        if change_request == 1:
            escalate("day")
        if gps_deviation > 5 or delay > 60:
            escalate("day")
        if num_affected >= 3:
            escalate("plan")

        if severity == SEVERITY_NONE:
            return LABEL_NORMAL, SEVERITY_NONE
        return LABEL_DISRUPTION, severity

    def apply_label_noise(
        self,
        labels: Sequence[str],
        severities: Sequence[str],
    ) -> Tuple[List[str], List[str]]:
        """Flip ``noise_rate`` of the labels and return the new sequences."""
        labels = list(labels)
        severities = list(severities)
        num_flips = int(round(len(labels) * self.noise_rate))
        if num_flips <= 0:
            return labels, severities

        rng = random.Random(self.seed)
        indices = rng.sample(range(len(labels)), num_flips)
        severities_pool = list(SEVERITY_LEVELS)

        for index in indices:
            if labels[index] == LABEL_NORMAL:
                labels[index] = LABEL_DISRUPTION
                severities[index] = rng.choice(severities_pool)
            else:
                labels[index] = LABEL_NORMAL
                severities[index] = SEVERITY_NONE

        return labels, severities

    def apply_noise_to_rows(self, rows: List[Dict[str, Any]]) -> int:
        """In-place noise injection over ``rows``; returns the flip count."""
        labels, severities = self.apply_label_noise(
            [row["label"] for row in rows],
            [row["severity"] for row in rows],
        )
        flips = sum(
            1
            for row, label in zip(rows, labels)
            if row["label"] != label
        )
        for row, label, severity in zip(rows, labels, severities):
            row["label"] = label
            row["severity"] = severity
        return flips


__all__ = ["DisruptionLabeler"]
