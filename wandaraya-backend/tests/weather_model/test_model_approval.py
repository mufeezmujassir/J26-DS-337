from types import SimpleNamespace

from app.weather_model.monitoring.approval import (
    ModelApprovalEvaluator,
    QualityMetrics,
)
from app.weather_model.monitoring.registry_audit import audit_model_runs


def _metrics(*, holdout_mae: float = 1.0, baselines=None) -> QualityMetrics:
    return QualityMetrics(
        validation_mae=1.0,
        validation_rmse=1.2,
        validation_months=24,
        validation_folds=2,
        holdout_mae=holdout_mae,
        holdout_rmse=1.2,
        holdout_months=10,
        baseline_holdout_mae=baselines or {
            "seasonal_naive": 1.5,
            "monthly_climatology": 1.6,
        },
    )


def test_missing_metrics_cannot_be_approved() -> None:
    decision = ModelApprovalEvaluator().evaluate(
        target="temperature_max_c",
        model_name="prophet",
        training_observations=48,
        validation_gate_passed=True,
        metrics=None,
    )
    assert decision.lifecycle_state == "insufficient_evidence"
    assert decision.eligible_for_review is False


def test_weak_holdout_is_rejected_even_when_validation_gate_passed() -> None:
    decision = ModelApprovalEvaluator().evaluate(
        target="temperature_max_c",
        model_name="prophet",
        training_observations=48,
        validation_gate_passed=True,
        metrics=_metrics(holdout_mae=3.0),
    )
    assert decision.lifecycle_state == "rejected"
    assert decision.eligible_for_review is False
    assert any("Holdout MAE" in reason for reason in decision.reasons)


def test_candidate_requires_human_review_after_passing_all_gates() -> None:
    decision = ModelApprovalEvaluator().evaluate(
        target="temperature_max_c",
        model_name="prophet",
        training_observations=48,
        validation_gate_passed=True,
        metrics=_metrics(),
    )
    assert decision.lifecycle_state == "candidate"
    assert decision.eligible_for_review is True
    assert decision.baseline_improvement_percent is not None


def test_audit_does_not_change_stored_approval_status() -> None:
    run = SimpleNamespace(
        run_id="run-1",
        district_id=78,
        target="temperature_max_c",
        model_name="prophet",
        training_observations=48,
        validation_gate_passed=True,
        production_approved=False,
        status="trained",
        parameters={
            "quality_metrics": {
                "validation_mae": 1.0,
                "validation_rmse": 1.2,
                "validation_months": 24,
                "validation_folds": 2,
                "holdout_mae": 1.0,
                "holdout_rmse": 1.2,
                "holdout_months": 10,
                "baseline_holdout_mae": {"seasonal_naive": 1.5},
            }
        },
    )
    report = audit_model_runs([run])
    assert run.production_approved is False
    assert report[0]["production_approved"] is False
    assert report[0]["decision"]["eligible_for_review"] is True
