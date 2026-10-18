"""Inference wrapper around the trained disruption-detection classifiers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app.replanning.disruption_detection.classifiers import FEATURE_NAMES

LOGGER = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "model_files"
DISRUPTION_MODEL_FILE = "disruption_classifier.pkl"
SEVERITY_MODEL_FILE = "severity_classifier.pkl"
SCALER_FILE = "disruption_scaler.pkl"

# Decision threshold on P(disruption) for the standalone presence model.
DISRUPTION_THRESHOLD = 0.5


class MLClassifier:
    """Serve predictions from the trained presence and severity models."""

    def __init__(self, model_dir: str | Path = "model_files") -> None:
        """Store the model directory; call :meth:`load_models` to load them."""
        candidate = Path(model_dir)
        if not candidate.is_absolute():
            candidate = DEFAULT_MODEL_DIR.parent / candidate
        self.model_dir: Path = candidate

        self.disruption_model: Optional[Any] = None
        self.severity_model: Optional[Any] = None
        self.scaler: Optional[Any] = None
        self._loaded = False

    def load_models(self) -> None:
        """Load the presence model, severity model and scaler from disk.

        Raises:
            FileNotFoundError: if any expected artefact is missing.
        """
        disruption_path = self.model_dir / DISRUPTION_MODEL_FILE
        severity_path = self.model_dir / SEVERITY_MODEL_FILE
        scaler_path = self.model_dir / SCALER_FILE

        missing = [
            path.name
            for path in (disruption_path, severity_path, scaler_path)
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "Missing ML model file(s) in "
                f"{self.model_dir}: {', '.join(missing)}. "
                "Train them first with:\n"
                "  python -m app.replanning.disruption_detection.classifiers."
                "train_disruption_classifier\n"
                "  python -m app.replanning.disruption_detection.classifiers."
                "train_severity_classifier"
            )

        self.disruption_model = joblib.load(disruption_path)
        self.severity_model = joblib.load(severity_path)
        self.scaler = joblib.load(scaler_path)
        self._loaded = True
        LOGGER.info("Loaded ML models from %s", self.model_dir)

    def _ensure_loaded(self) -> None:
        """Load models on first use if the caller forgot to call load."""
        if not self._loaded:
            self.load_models()

    @staticmethod
    def _vectorize(features: Dict[str, Any]) -> np.ndarray:
        """Build a single-row feature matrix in the canonical feature order."""
        row: List[float] = []
        for name in FEATURE_NAMES:
            value = features.get(name, 0.0)
            if isinstance(value, bool):
                row.append(float(int(value)))
            else:
                try:
                    row.append(float(value))
                except (TypeError, ValueError):
                    LOGGER.warning(
                        "Feature %s=%r is not numeric; using 0.0",
                        name,
                        value,
                    )
                    row.append(0.0)
        return np.asarray([row], dtype=float)

    def predict_disruption(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict whether ``features`` describe a disruption.

        Returns:
            ``{"is_disruption": bool, "probability": float}`` where
            ``probability`` is P(disruption).
        """
        self._ensure_loaded()
        vector = self._vectorize(features)
        scaled = self.scaler.transform(vector)
        probability = float(
            self.disruption_model.predict_proba(scaled)[0, 1]
        )
        is_disruption = probability >= DISRUPTION_THRESHOLD

        LOGGER.info(
            "ML disruption prediction: p=%.4f is_disruption=%s",
            probability,
            is_disruption,
        )
        return {
            "is_disruption": bool(is_disruption),
            "probability": round(probability, 4),
        }

    def predict_severity(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict the severity class (``step`` / ``day`` / ``plan``).

        Returns:
            ``{"severity": str, "confidence": float}`` where ``confidence``
            is the class probability of the predicted severity.
        """
        self._ensure_loaded()
        vector = self._vectorize(features)
        probabilities = self.severity_model.predict_proba(vector)[0]
        classes = list(self.severity_model.classes_)
        index = int(np.argmax(probabilities))
        severity = str(classes[index])
        confidence = float(probabilities[index])

        LOGGER.info(
            "ML severity prediction: severity=%s confidence=%.4f",
            severity,
            confidence,
        )
        return {
            "severity": severity,
            "confidence": round(confidence, 4),
        }

    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Run both models and return a combined prediction payload.

        Returns:
            ``{"is_disruption", "probability", "severity", "confidence",
            "ml_severity"}``. ``severity`` is the raw Random Forest class;
            consumers decide whether to apply it based on ``is_disruption``.
        """
        disruption = self.predict_disruption(features)
        severity = self.predict_severity(features)
        return {
            "is_disruption": disruption["is_disruption"],
            "probability": disruption["probability"],
            "severity": severity["severity"],
            "confidence": severity["confidence"],
            "ml_severity": severity["severity"],
        }


__all__ = [
    "MLClassifier",
    "DEFAULT_MODEL_DIR",
    "DISRUPTION_THRESHOLD",
]