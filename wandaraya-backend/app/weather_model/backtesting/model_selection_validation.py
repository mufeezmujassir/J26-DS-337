"""Validate paired backtests and make non-production model recommendations.

This module consumes existing benchmark artifacts only.  It does not retrain a
model, write weather observations, or approve a model for production.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPORT_DIR = Path("data/weather/reports/backtesting")
NATIONAL_REPORT = REPORT_DIR / "national_benchmark_report.json"
EVIDENCE_REPORT = REPORT_DIR / "model_selection_evidence.json"
OUTPUT_REPORT = REPORT_DIR / "model_selection_validation.json"
MODELS = ("monthly_climatology", "seasonal_naive", "prophet")

# These are deliberately review thresholds, not a claim of statistical
# significance.  The small number of rolling origins makes that distinction
# important for research reporting.
TIE_RELATIVE_MAE_PERCENT = 2.0
PROPHET_CLEAR_IMPROVEMENT_PERCENT = 5.0
BIAS_TO_MAE_REVIEW_RATIO = 0.5


def series_key(item: Mapping[str, Any]) -> tuple[int, str]:
    return int(item["district_id"]), str(item["target"])


def prediction_key(prediction: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(prediction["origin"]),
        str(prediction["target_month"]),
        int(prediction["horizon"]),
    )


def validate_paired_predictions(
    detailed_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify every model used the same prediction pairs and actual values."""
    model_predictions = {
        model: detailed_report.get("results", {}).get(model, {}).get("predictions", [])
        for model in MODELS
    }
    keyed: dict[str, dict[tuple[str, str, int], float]] = {}
    duplicate_keys: dict[str, bool] = {}
    for model, predictions in model_predictions.items():
        values: dict[tuple[str, str, int], float] = {}
        duplicate_keys[model] = False
        for prediction in predictions:
            key = prediction_key(prediction)
            if key in values:
                duplicate_keys[model] = True
            values[key] = float(prediction["actual"])
        keyed[model] = values

    key_sets = [set(keyed[model]) for model in MODELS]
    common_keys = set.intersection(*key_sets)
    same_keys = all(keys == key_sets[0] for keys in key_sets)
    same_actuals = all(
        keyed[model].get(key) == keyed[MODELS[0]].get(key)
        for model in MODELS[1:]
        for key in common_keys
    )
    paired = bool(common_keys) and same_keys and same_actuals and not any(duplicate_keys.values())
    horizons = sorted({key[2] for key in common_keys})
    return {
        "paired_observed_targets_valid": paired,
        "shared_prediction_count": len(common_keys),
        "prediction_counts": {model: len(keyed[model]) for model in MODELS},
        "horizons_present": horizons,
        "duplicate_prediction_keys": duplicate_keys,
        "reason": (
            None
            if paired
            else "No complete identical observed prediction set is available across all models."
        ),
    }


def relative_improvement(candidate_mae: float | None, baseline_mae: float | None) -> float | None:
    if candidate_mae is None or baseline_mae is None or baseline_mae <= 0:
        return None
    return round((baseline_mae - candidate_mae) / baseline_mae * 100, 2)


def validate_series(
    evidence: Mapping[str, Any], detailed_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Return transparent recommendation evidence for one district-target pair."""
    pairing = validate_paired_predictions(detailed_report)
    metrics = evidence.get("model_metrics", {})
    folds = int(evidence.get("independent_rolling_origin_folds", 0))
    metric_values = {
        model: metrics.get(model, {}) for model in MODELS
    }
    available = {
        model: values for model, values in metric_values.items() if values.get("mae") is not None
    }
    review_flags: list[str] = []

    if not pairing["paired_observed_targets_valid"]:
        review_flags.append("paired_prediction_validation_failed")
    if folds == 0 or not available:
        evidence_status = "insufficient_evidence"
        provisional_candidate = None
        recommendation = "insufficient_evidence"
        review_flags.append("no_valid_folds_or_predictions")
    elif folds < 5:
        evidence_status = "limited_evidence"
        provisional_candidate = min(available, key=lambda model: available[model]["mae"])
        recommendation = "limited_evidence"
        review_flags.append("fewer_than_five_independent_folds")
    else:
        evidence_status = "eligible_for_review"
        provisional_candidate = min(available, key=lambda model: available[model]["mae"])
        recommendation = None

    ranked = sorted(available, key=lambda model: available[model]["mae"])
    best_mae = available[provisional_candidate]["mae"] if provisional_candidate else None
    runner_up = ranked[1] if len(ranked) > 1 else None
    runner_up_mae = available[runner_up]["mae"] if runner_up else None
    advantage_over_runner_up = relative_improvement(best_mae, runner_up_mae)
    prophet_vs_climatology = relative_improvement(
        metric_values["prophet"].get("mae"),
        metric_values["monthly_climatology"].get("mae"),
    )

    if evidence_status == "eligible_for_review":
        if advantage_over_runner_up is not None and advantage_over_runner_up <= TIE_RELATIVE_MAE_PERCENT:
            recommendation = "tie_requires_review"
            review_flags.append("best_and_second_best_mae_are_nearly_identical")
        elif provisional_candidate == "prophet":
            if (
                prophet_vs_climatology is not None
                and prophet_vs_climatology >= PROPHET_CLEAR_IMPROVEMENT_PERCENT
            ):
                recommendation = "prophet_candidate"
            else:
                recommendation = "marginal_improvement_requires_review"
                review_flags.append("prophet_improvement_below_clear_candidate_threshold")
        elif provisional_candidate == "monthly_climatology":
            recommendation = "climatology_candidate"
        else:
            recommendation = "seasonal_naive_candidate"

    bias_flags: dict[str, bool] = {}
    for model, values in metric_values.items():
        mae, bias = values.get("mae"), values.get("bias")
        bias_flags[model] = bool(
            mae is not None and bias is not None and mae > 0 and abs(bias) / mae >= BIAS_TO_MAE_REVIEW_RATIO
        )
    if provisional_candidate and bias_flags.get(provisional_candidate):
        review_flags.append("selected_model_has_large_systematic_bias")
        if evidence_status == "eligible_for_review":
            recommendation = "bias_review_required"

    horizon_checks = {
        model: {
            str(horizon): metric_values[model].get("metrics_by_horizon", {}).get(str(horizon))
            for horizon in (1, 2, 3)
        }
        for model in MODELS
    }
    if available and any(
        any(values[str(horizon)] is None for horizon in (1, 2, 3))
        for values in horizon_checks.values()
        if values
    ):
        review_flags.append("incomplete_horizon_error_evidence")

    return {
        "district_id": evidence["district_id"],
        "target": evidence["target"],
        "evidence_status": evidence_status,
        "independent_rolling_origin_folds": folds,
        "paired_prediction_validation": pairing,
        "model_metrics": metric_values,
        "horizon_error_checks": horizon_checks,
        "mae_comparison": {
            "ranked_models": ranked,
            "best_model": provisional_candidate,
            "best_mae": best_mae,
            "runner_up_model": runner_up,
            "advantage_over_runner_up_percent": advantage_over_runner_up,
            "prophet_improvement_over_climatology_percent": prophet_vs_climatology,
        },
        "systematic_bias_flags": bias_flags,
        "provisional_candidate": provisional_candidate,
        "recommendation": recommendation,
        "review_flags": review_flags,
        "training_policy": evidence.get("training_policy", {}),
        "imputed_training_folds": evidence.get("imputed_training_folds", 0),
        "production_approved": False,
    }


def build_validation(
    national: Mapping[str, Any], evidence_report: Mapping[str, Any], report_dir: Path,
) -> dict[str, Any]:
    national_keys = {series_key(item) for item in national.get("results", [])}
    evidence_by_key = {series_key(item): item for item in evidence_report.get("series", [])}
    results: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []

    for key in sorted(national_keys):
        evidence = evidence_by_key.get(key)
        if evidence is None:
            unavailable.append({"district_id": key[0], "target": key[1], "reason": "missing_evidence"})
            continue
        path = report_dir / f"district_{key[0]}_{key[1]}_backtest.json"
        try:
            detailed = json.loads(path.read_text(encoding="utf-8"))
            results.append(validate_series(evidence, detailed))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            unavailable.append({"district_id": key[0], "target": key[1], "reason": str(exc)})

    status_counts = Counter(item["evidence_status"] for item in results)
    recommendation_counts = Counter(item["recommendation"] for item in results)
    return {
        "stage": "9.8.7.8",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_reports": {
            "national_benchmark": str(NATIONAL_REPORT),
            "model_selection_evidence": str(EVIDENCE_REPORT),
        },
        "selection_policy": {
            "minimum_folds_for_review": 5,
            "tie_relative_mae_percent": TIE_RELATIVE_MAE_PERCENT,
            "prophet_clear_improvement_percent": PROPHET_CLEAR_IMPROVEMENT_PERCENT,
            "large_bias_to_mae_ratio": BIAS_TO_MAE_REVIEW_RATIO,
            "statistical_significance_claimed": False,
        },
        "summary": {
            "national_series": len(national_keys),
            "validated_series": len(results),
            "evidence_statuses": dict(sorted(status_counts.items())),
            "recommendations": dict(sorted(recommendation_counts.items())),
            "unavailable_series": len(unavailable),
        },
        "series": results,
        "unavailable_series": unavailable,
        "production_approved": False,
        "note": (
            "This is paired point-estimate evidence, not a significance test. "
            "Detailed reports retain prediction-level records for future paired confidence intervals."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--national-report", type=Path, default=NATIONAL_REPORT)
    parser.add_argument("--evidence-report", type=Path, default=EVIDENCE_REPORT)
    parser.add_argument("--output", type=Path, default=OUTPUT_REPORT)
    arguments = parser.parse_args()

    national = json.loads(arguments.national_report.read_text(encoding="utf-8"))
    evidence = json.loads(arguments.evidence_report.read_text(encoding="utf-8"))
    validation = build_validation(national, evidence, arguments.national_report.parent)
    arguments.output.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print("\n=== MODEL-SELECTION VALIDATION ===")
    print(json.dumps(validation["summary"], indent=2))
    print("Production approved:", validation["production_approved"])
    print("Report:", arguments.output)


if __name__ == "__main__":
    main()
