"""Explain zero-prediction and failed jobs in a national benchmark report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


REPORT_PATH = Path("data/weather/reports/backtesting/national_benchmark_report.json")


def diagnose_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Produce a read-only, serializable diagnosis from an existing report."""
    results = report.get("results", [])
    failures = report.get("failures", [])
    skipped = report.get("skipped", [])
    completed = [
        item
        for item in results
        if item.get("fair_comparison_status") == "completed"
        and item.get("common_prediction_count", 0) > 0
    ]
    no_common = [
        item for item in results if item.get("common_prediction_count", 0) == 0
    ]
    reasons = Counter(
        skipped_fold.get("reason", "unknown")
        for item in no_common
        for skipped_fold in item.get("skipped_folds", [])
    )
    return {
        "reports_loaded": len(results),
        "completed_comparisons": len(completed),
        "zero_common_prediction_series": len(no_common),
        "execution_or_report_failures": len(failures),
        "preliminary_exclusions": len(skipped),
        "zero_prediction_reason_counts": dict(sorted(reasons.items())),
        "zero_prediction_series": [
            {
                "district_id": item.get("district_id"),
                "target": item.get("target"),
                "observation_count": item.get("observation_count"),
                "skipped_folds": item.get("skipped_folds", []),
            }
            for item in no_common
        ],
        "failures": failures,
        "preliminary_exclusions_detail": skipped,
    }


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    diagnosis = diagnose_report(report)
    print("\n=== NATIONAL BENCHMARK DIAGNOSTICS ===")
    print("Reports loaded:", diagnosis["reports_loaded"])
    print("Completed comparisons:", diagnosis["completed_comparisons"])
    print("Zero-common-prediction series:", diagnosis["zero_common_prediction_series"])
    print("Execution/report failures:", diagnosis["execution_or_report_failures"])
    print("Preliminary exclusions:", diagnosis["preliminary_exclusions"])
    print("\n=== ZERO-PREDICTION REASONS ===")
    print(json.dumps(diagnosis["zero_prediction_reason_counts"], indent=2))
    print("\n=== ZERO-PREDICTION SERIES ===")
    for item in diagnosis["zero_prediction_series"]:
        print(json.dumps(item, indent=2))
    if diagnosis["failures"]:
        print("\n=== EXECUTION OR REPORT FAILURES ===")
        for item in diagnosis["failures"]:
            print(json.dumps(item, indent=2))


if __name__ == "__main__":
    main()
