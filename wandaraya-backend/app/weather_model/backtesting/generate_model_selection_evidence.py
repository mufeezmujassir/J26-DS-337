"""Create provisional, reviewable model-selection evidence from backtest reports."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPORT_DIR = Path("data/weather/reports/backtesting")
NATIONAL_REPORT = REPORT_DIR / "national_benchmark_report.json"
OUTPUT_REPORT = REPORT_DIR / "model_selection_evidence.json"
MODELS = ("monthly_climatology", "seasonal_naive", "prophet")


def evidence_level(fold_count: int, common_prediction_count: int) -> str:
    if common_prediction_count == 0 or fold_count == 0:
        return "insufficient"
    if fold_count == 1:
        return "limited"
    if fold_count < 3:
        return "preliminary"
    return "stronger"


def summarize_backtest(report: Mapping[str, Any]) -> dict[str, Any]:
    """Extract comparable metrics and traceable missing-data evidence."""
    fair_comparison = report.get("fair_comparison", {})
    comparison = fair_comparison.get("comparison", {})
    results = report.get("results", {})
    reference = results.get("prophet", {})
    fold_count = int(reference.get("fold_count", 0))
    common_prediction_count = int(fair_comparison.get("common_prediction_count", 0))

    metrics = {
        model: {
            "mae": comparison.get(model, {}).get("mae"),
            "rmse": comparison.get(model, {}).get("rmse"),
            "bias": comparison.get(model, {}).get("bias"),
            "prediction_count": comparison.get(model, {}).get("prediction_count", 0),
            "metrics_by_horizon": comparison.get(model, {}).get("metrics_by_horizon", {}),
            "improvement_over_monthly_climatology_percent": comparison.get(model, {}).get(
                "improvement_over_monthly_climatology_percent"
            ),
        }
        for model in MODELS
    }
    eligible_models = {
        model: value for model, value in metrics.items() if value["mae"] is not None
    }
    recommendation = (
        min(eligible_models, key=lambda model: eligible_models[model]["mae"])
        if fair_comparison.get("status") == "completed" and len(eligible_models) == len(MODELS)
        else None
    )

    return {
        "district_id": report["district_id"],
        "target": report["target"],
        "fair_comparison_status": fair_comparison.get("status"),
        "common_prediction_count": common_prediction_count,
        "independent_rolling_origin_folds": fold_count,
        "evidence_level": evidence_level(fold_count, common_prediction_count),
        "model_metrics": metrics,
        "training_policy": report.get("training_policy", {}),
        "imputed_training_folds": sum(
            bool(item.get("imputed_months"))
            for item in reference.get("fold_metadata", [])
        ),
        "skipped_folds": reference.get("skipped_folds", []),
        "provisional_recommendation": recommendation,
        "production_approved": False,
    }


def build_evidence(national_report: Mapping[str, Any], report_dir: Path) -> dict[str, Any]:
    """Read the detailed reports named by the benchmark and preserve failures."""
    entries: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for item in national_report.get("results", []):
        district_id, target = item["district_id"], item["target"]
        path = report_dir / f"district_{district_id}_{target}_backtest.json"
        try:
            detailed = json.loads(path.read_text(encoding="utf-8"))
            entries.append(summarize_backtest(detailed))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            unavailable.append(
                {"district_id": district_id, "target": target, "reason": str(exc)}
            )

    levels = Counter(item["evidence_level"] for item in entries)
    return {
        "stage": "9.8.7.6",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_national_benchmark": str(NATIONAL_REPORT),
        "summary": {
            "series_considered": len(national_report.get("results", [])),
            "series_with_detailed_evidence": len(entries),
            "evidence_levels": dict(sorted(levels.items())),
            "unavailable_detailed_reports": len(unavailable),
        },
        "series": sorted(entries, key=lambda item: (item["district_id"], item["target"])),
        "unavailable_detailed_reports": unavailable,
        "production_approved": False,
        "note": (
            "Recommendations are provisional research evidence only. "
            "Production approval remains a separate quality-gate decision."
        ),
    }


def main() -> None:
    national_report = json.loads(NATIONAL_REPORT.read_text(encoding="utf-8"))
    evidence = build_evidence(national_report, REPORT_DIR)
    OUTPUT_REPORT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("\n=== MODEL SELECTION EVIDENCE ===")
    print(json.dumps(evidence["summary"], indent=2))
    print("Report:", OUTPUT_REPORT)


if __name__ == "__main__":
    main()
