"""Random Forest intent-preservation classifier inference wrapper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app.replanning.dynamic_replanning.classifiers import (
    DECISION_THRESHOLD,
    FEATURE_NAMES,
    MODEL_DIR,
    MODEL_FILENAME,
    extract_features as _extract_features,
    feature_matrix,
)

LOGGER = logging.getLogger(__name__)


class IntentClassifier:
    def __init__(self, model_dir: str | Path = "model_files") -> None:
        candidate = Path(model_dir)
        if not candidate.is_absolute():
            candidate = MODEL_DIR.parent / candidate
        self.model_dir = candidate
        self.model: Optional[Any] = None
        self._loaded = False

    def load_model(self) -> None:
        path = self.model_dir / MODEL_FILENAME
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing intent classifier model in {self.model_dir}: {MODEL_FILENAME}. "
                "Train it with: python -m app.replanning.dynamic_replanning.classifiers.train_intent_classifier"
            )
        self.model = joblib.load(path)
        self._loaded = True
        LOGGER.info("Loaded intent classifier model from %s", path)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_model()

    @staticmethod
    def _vectorize(features: Dict[str, Any]) -> np.ndarray:
        row = []
        for name in FEATURE_NAMES:
            v = features.get(name, 0.0)
            if isinstance(v, bool):
                row.append(float(int(v)))
            else:
                try:
                    row.append(float(v))
                except Exception:
                    LOGGER.warning("Feature %s=%r not numeric; using 0.0", name, v)
                    row.append(0.0)
        return np.asarray([row], dtype=float)

    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_loaded()
        vector = self._vectorize(features)
        prob = float(self.model.predict_proba(vector)[0, 1])
        intent_preserved = prob >= DECISION_THRESHOLD
        LOGGER.info("Intent prediction: prob=%.4f preserved=%s", prob, intent_preserved)
        return {
            "intent_preserved": bool(intent_preserved),
            "probability": round(prob, 4),
            "model_used": "random_forest",
        }

    def predict_batch(self, features_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        X = np.asarray(feature_matrix(features_list), dtype=float)
        probs = self.model.predict_proba(X)[:, 1]
        out = []
        for p in probs:
            prob = float(p)
            out.append(
                {
                    "intent_preserved": bool(prob >= DECISION_THRESHOLD),
                    "probability": round(prob, 4),
                    "model_used": "random_forest",
                }
            )
        return out

    @staticmethod
    def extract_features(original: Dict[str, Any], disruption: Dict[str, Any], revised: Dict[str, Any]) -> Dict[str, Any]:
        from app.replanning.dynamic_replanning.classifiers._feature_extractor import extract_features as fe

        return fe(original, disruption, revised)
