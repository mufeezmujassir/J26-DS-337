"""Rule-based drift labeling with controlled label noise.

Any hard-rule violation of a prior constraint labels the row as drift (1);
otherwise the row is consistent (0). 5% of labels are then flipped
deterministically (seed 42) to simulate real-world annotation noise.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.classifiers.consistency import (
    LABEL_CONSISTENT,
    LABEL_DRIFT,
    LABEL_NOISE_RATE,
    DEFAULT_SEED,
)

from app.replanning.dynamic_replanning.classifiers.consistency._feature_extractor import (
    detect_violations,
)

__all__ = ["DriftLabeler"]


class DriftLabeler:
    """Label (conversation, new_plan) pairs with drift rules plus noise."""

    def __init__(self, noise_rate: float = LABEL_NOISE_RATE, seed: int = DEFAULT_SEED) -> None:
        self.noise_rate = noise_rate
        self.seed = seed
        self.rng = random.Random(seed)

    def label(
        self,
        conversation: Dict[str, Any],
        new_plan: Dict[str, Any],
        features: Dict[str, Any],
    ) -> int:
        """Return LABEL_DRIFT (1) when any prior constraint is violated."""

        violations = detect_violations(conversation, new_plan)
        if violations:
            return LABEL_DRIFT

        if int(features.get("num_conflicting_constraints", 0)) > 0:
            return LABEL_DRIFT

        return LABEL_CONSISTENT

    def apply_label_noise(self, labels: List[int]) -> List[int]:
        """Flip ``noise_rate`` of the labels (deterministic under the seed)."""

        if not labels:
            return list(labels)
        num_flips = int(round(len(labels) * self.noise_rate))
        indices = self.rng.sample(range(len(labels)), num_flips)
        out = list(labels)
        for idx in indices:
            out[idx] = (
                LABEL_DRIFT if out[idx] == LABEL_CONSISTENT else LABEL_CONSISTENT
            )
        return out
