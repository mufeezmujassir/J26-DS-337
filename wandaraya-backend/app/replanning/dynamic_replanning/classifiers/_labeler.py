"""Rule-based intent labeling with controlled label noise."""

from __future__ import annotations

import random
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.classifiers import (
    BUDGET_OVERRUN_THRESHOLD,
    LABEL_BROKEN,
    LABEL_PRESERVED,
    LOCATION_SHIFT_THRESHOLD_KM,
    MIN_MINOR_CHANGES,
    TIME_SHIFT_THRESHOLD_MINUTES,
)

__all__ = ["IntentLabeler"]


class IntentLabeler:
    def __init__(self, noise_rate: float = 0.05, seed: int = 42) -> None:
        self.noise_rate = noise_rate
        self.seed = seed
        self.rng = random.Random(seed)

    def label(
        self,
        original: Dict[str, Any],
        disruption: Dict[str, Any],
        revised: Dict[str, Any],
        features: Dict[str, Any],
    ) -> int:
        f = features

        # Hard rules (any broken => 0)
        if f.get("bookings_preserved_ratio", 1.0) < 1.0 - 1e-9:
            return LABEL_BROKEN
        if f.get("must_see_preserved_ratio", 1.0) < 1.0 - 1e-9:
            return LABEL_BROKEN
        if (
            f.get("vibe_match", 1) == 0
            and f.get("user_explicitly_changed_vibe", 0) == 0
        ):
            return LABEL_BROKEN
        if (
            f.get("budget_diff_ratio", 0.0) > BUDGET_OVERRUN_THRESHOLD
            and f.get("user_explicitly_changed_budget", 0) == 0
        ):
            return LABEL_BROKEN
        if f.get("time_shift_minutes", 0.0) > TIME_SHIFT_THRESHOLD_MINUTES + 1e-9:
            return LABEL_BROKEN
        if f.get("location_distance_km", 0.0) > LOCATION_SHIFT_THRESHOLD_KM + 1e-9:
            return LABEL_BROKEN
        if (
            f.get("num_activities_changed", 0) >= MIN_MINOR_CHANGES
            and f.get("user_explicitly_changed_vibe", 0) == 0
            and f.get("user_explicitly_changed_budget", 0) == 0
        ):
            return LABEL_BROKEN

        return LABEL_PRESERVED

    def apply_label_noise(self, labels: List[int]) -> List[int]:
        if not labels:
            return list(labels)
        n = len(labels)
        num_flips = int(round(n * self.noise_rate))
        indices = self.rng.sample(range(n), num_flips)
        out = list(labels)
        for idx in indices:
            out[idx] = LABEL_BROKEN if out[idx] == LABEL_PRESERVED else LABEL_PRESERVED
        return out
