"""Central, experimental parameters for suitability-score calibration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationConfig:
    neutral_score: float = 50.0
    # Initial research hypotheses; these are not fitted model coefficients.
    live_base_quality: float = 0.90
    monthly_base_quality: float = 0.55
    climatology_base_quality: float = 0.35
    missing_target_penalty: float = 0.12
    min_score: float = 0.0
    max_score: float = 100.0


DEFAULT_CALIBRATION = CalibrationConfig()
