"""Random Forest cross-turn consistency classifier inference wrapper.

Loads the  model (``consistency_classifier_rf.pkl``) and
predicts intent drift from the 12 simulated features. 
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app.replanning.dynamic_replanning.classifiers.consistency import (
    CONSISTENCY_MODEL_DIR,
    CONSISTENCY_MODEL_FILENAME,
    DECISION_THRESHOLD,
    FEATURE_NAMES,
)

LOGGER = logging.getLogger(__name__)


class ConsistencyClassifier:
    """Inference wrapper for the production consistency Random Forest."""

    def __init__(self, model_dir: str | Path = "model_files") -> None:
        candidate = Path(model_dir)
        if not candidate.is_absolute():
            candidate = CONSISTENCY_MODEL_DIR.parent / candidate
        self.model_dir = candidate
        self.model: Optional[Any] = None
        self._loaded = False

    def load_model(self) -> None:
        """Load the RF model; raise a clear error when it is missing."""

        path = self.model_dir / CONSISTENCY_MODEL_FILENAME
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing consistency classifier model in {self.model_dir}: "
                f"{CONSISTENCY_MODEL_FILENAME}. Train it with: python -m "
                "app.replanning.dynamic_replanning.classifiers.consistency."
                "train_consistency_classifier"
            )
        self.model = joblib.load(path)
        self._loaded = True
        LOGGER.info("Loaded consistency classifier model from %s", path)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_model()

    @staticmethod
    def _vectorize(features: Dict[str, Any]) -> np.ndarray:
        row = []
        for name in FEATURE_NAMES:
            value = features.get(name, 0.0)
            if isinstance(value, bool):
                row.append(float(int(value)))
            else:
                try:
                    row.append(float(value))
                except (TypeError, ValueError):
                    LOGGER.warning(
                        "Feature %s=%r not numeric; using 0.0", name, value
                    )
                    row.append(0.0)
        return np.asarray([row], dtype=float)

    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict drift for a single feature dict.

        Returns ``{"drift_detected", "probability", "model_used"}``.
        """

        self._ensure_loaded()
        vector = self._vectorize(features)
        probability = float(self.model.predict_proba(vector)[0, 1])
        drift_detected = probability >= DECISION_THRESHOLD
        LOGGER.info(
            "Consistency prediction: prob=%.4f drift_detected=%s",
            probability,
            drift_detected,
        )
        return {
            "drift_detected": bool(drift_detected),
            "probability": round(probability, 4),
            "model_used": "random_forest",
        }

    def predict_batch(
        self, features_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Predict drift for a batch of feature dicts."""

        self._ensure_loaded()
        matrix = np.asarray(
            [self._vectorize(f).ravel() for f in features_list], dtype=float
        )
        probabilities = self.model.predict_proba(matrix)[:, 1]
        results: List[Dict[str, Any]] = []
        for value in probabilities:
            probability = float(value)
            results.append(
                {
                    "drift_detected": bool(probability >= DECISION_THRESHOLD),
                    "probability": round(probability, 4),
                    "model_used": "random_forest",
                }
            )
        LOGGER.info(
            "Batch consistency prediction: %d rows, %d drift detected",
            len(results),
            sum(1 for r in results if r["drift_detected"]),
        )
        return results


__all__ = ["ConsistencyClassifier"]
