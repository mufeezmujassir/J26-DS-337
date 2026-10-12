"""Conservative, side-effect-free quality gates for monthly forecast models.

This module deliberately never changes ``production_approved``.  A model can
only become *eligible for human review* here; the separate review command is
the sole path that can make an explicit approval decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping


BASELINE_MODELS = frozenset({"seasonal_naive", "monthly_climatology"})


@dataclass(frozen=True)
class TargetApprovalRule:
    """Research defaults for a target, intentionally kept configurable in code."""

    min_training_observations: int
    min_validation_folds: int
    min_validation_months: int
    min_holdout_months: int
    max_holdout_mae: float
    max_holdout_rmse: float
    min_baseline_improvement_percent: float = 0.0


# These are screening limits, not a claim that forecasts below them are safe
# for every tourism decision.  They are applied only before human review.
DEFAULT_TARGET_RULES: dict[str, TargetApprovalRule] = {
    "rainfall_mm": TargetApprovalRule(36, 2, 20, 9, 75.0, 110.0),
    "temperature_min_c": TargetApprovalRule(36, 2, 20, 9, 2.5, 3.5),
    "temperature_max_c": TargetApprovalRule(36, 2, 20, 9, 2.5, 3.5),
}


@dataclass(frozen=True)
class QualityMetrics:
    """Selected-model and baseline measurements from an isolated holdout."""

    validation_mae: float | None
    validation_rmse: float | None
    validation_months: int | None
    validation_folds: int | None
    holdout_mae: float | None
    holdout_rmse: float | None
    holdout_months: int | None
    baseline_holdout_mae: Mapping[str, float]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "QualityMetrics | None":
        if not isinstance(value, Mapping):
            return None

        def number(name: str) -> float | None:
            raw = value.get(name)
            return float(raw) if raw is not None else None

        def integer(name: str) -> int | None:
            raw = value.get(name)
            return int(raw) if raw is not None else None

        raw_baselines = value.get("baseline_holdout_mae", {})
        if not isinstance(raw_baselines, Mapping):
            raw_baselines = {}
        baselines = {
            str(name): float(score)
            for name, score in raw_baselines.items()
            if score is not None
        }
        return cls(
            validation_mae=number("validation_mae"),
            validation_rmse=number("validation_rmse"),
            validation_months=integer("validation_months"),
            validation_folds=integer("validation_folds"),
            holdout_mae=number("holdout_mae"),
            holdout_rmse=number("holdout_rmse"),
            holdout_months=integer("holdout_months"),
            baseline_holdout_mae=baselines,
        )


@dataclass(frozen=True)
class ApprovalDecision:
    """An audit result.  ``eligible_for_review`` is never production approval."""

    lifecycle_state: str
    eligible_for_review: bool
    reasons: tuple[str, ...]
    baseline_improvement_percent: float | None


class ModelApprovalEvaluator:
    """Apply transparent quality checks without mutating a model registry row."""

    def __init__(
        self,
        rules: Mapping[str, TargetApprovalRule] | None = None,
    ) -> None:
        self.rules = dict(rules or DEFAULT_TARGET_RULES)

    def evaluate(
        self,
        *,
        target: str,
        model_name: str,
        training_observations: int,
        validation_gate_passed: bool,
        metrics: QualityMetrics | None,
    ) -> ApprovalDecision:
        rule = self.rules.get(target)
        if rule is None:
            return ApprovalDecision(
                "insufficient_evidence",
                False,
                (f"No approval rule is configured for target '{target}'.",),
                None,
            )

        reasons: list[str] = []
        if not validation_gate_passed:
            reasons.append("The existing validation gate did not pass.")
        if training_observations < rule.min_training_observations:
            reasons.append(
                f"Only {training_observations} training observations; "
                f"requires at least {rule.min_training_observations}."
            )
        if metrics is None:
            return ApprovalDecision(
                "insufficient_evidence",
                False,
                tuple(reasons + ["No persisted quality metrics are available for this run."]),
                None,
            )

        required = {
            "validation MAE": metrics.validation_mae,
            "validation RMSE": metrics.validation_rmse,
            "validation months": metrics.validation_months,
            "validation folds": metrics.validation_folds,
            "holdout MAE": metrics.holdout_mae,
            "holdout RMSE": metrics.holdout_rmse,
            "holdout months": metrics.holdout_months,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            return ApprovalDecision(
                "insufficient_evidence",
                False,
                tuple(reasons + [f"Missing persisted {', '.join(missing)}."]),
                None,
            )

        if metrics.validation_folds < rule.min_validation_folds:
            reasons.append("Too few independent validation folds.")
        if metrics.validation_months < rule.min_validation_months:
            reasons.append("Too few validation months.")
        if metrics.holdout_months < rule.min_holdout_months:
            reasons.append("Too few held-out months.")
        if metrics.holdout_mae > rule.max_holdout_mae:
            reasons.append("Holdout MAE exceeds the configured target limit.")
        if metrics.holdout_rmse > rule.max_holdout_rmse:
            reasons.append("Holdout RMSE exceeds the configured target limit.")

        improvement: float | None = None
        if model_name not in BASELINE_MODELS:
            baseline_scores = [
                score
                for name, score in metrics.baseline_holdout_mae.items()
                if name in BASELINE_MODELS
            ]
            if not baseline_scores:
                return ApprovalDecision(
                    "insufficient_evidence",
                    False,
                    tuple(reasons + ["No comparable baseline holdout score is persisted."]),
                    None,
                )
            best_baseline = min(baseline_scores)
            if best_baseline <= 0:
                return ApprovalDecision(
                    "insufficient_evidence",
                    False,
                    tuple(reasons + ["Baseline holdout MAE must be greater than zero."]),
                    None,
                )
            improvement = 100 * (best_baseline - metrics.holdout_mae) / best_baseline
            if improvement < rule.min_baseline_improvement_percent:
                reasons.append(
                    "Selected model does not improve on the strongest established baseline."
                )

        if reasons:
            return ApprovalDecision("rejected", False, tuple(reasons), improvement)
        return ApprovalDecision(
            "candidate",
            True,
            ("Passed automated research gates; explicit human review is still required.",),
            improvement,
        )
