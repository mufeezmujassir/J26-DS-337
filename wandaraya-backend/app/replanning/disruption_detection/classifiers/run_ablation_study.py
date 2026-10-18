"""Source-removal ablation study on the frozen test split."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    FEATURE_NAMES,
    MODEL_DIR,
    SOURCE_FEATURES,
    load_jsonl,
)
from app.replanning.disruption_detection.classifiers._evaluation import (  # noqa: E402
    build_result,
    make_record,
    run_hybrid,
    run_ml,
    run_rules,
    save_result,
)
from app.replanning.disruption_detection.fusion import FusionEngine  # noqa: E402
from app.replanning.disruption_detection.ml_classifier import (  # noqa: E402
    MLClassifier,
)

LOGGER = logging.getLogger("run_ablation_study")
RESULTS_FILENAME = "results_ablation.json"

# Sources removed one at a time to build the hybrid_minus_* variants.
ABLATION_SOURCES = ("weather", "places", "complaint", "gps")


def _training_medians(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Return the per-feature median over the training rows."""
    medians: Dict[str, float] = {}
    for name in FEATURE_NAMES:
        values = [float(row.get(name, 0.0)) for row in rows]
        medians[name] = float(np.median(values))
    return medians


def _masked_row(
    row: Dict[str, Any], source: str, medians: Dict[str, float]
) -> Dict[str, Any]:
    """Copy ``row`` with all features of ``source`` replaced by medians."""
    masked = dict(row)
    for feature in SOURCE_FEATURES[source]:
        masked[feature] = medians[feature]
    return masked


def _f1_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the headline metrics from a result payload."""
    presence = payload["presence"]
    return {
        "accuracy": presence["accuracy"],
        "precision": presence["precision"],
        "recall": presence["recall"],
        "f1": presence["f1"],
        "roc_auc": presence["roc_auc"],
    }


def _markdown_table(rows: List[Dict[str, Any]]) -> str:
    """Render the ablation results as a Markdown table."""
    header = (
        "| Variant | Accuracy | Precision | Recall | F1 | ROC-AUC |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    lines = [header]
    for entry in rows:
        lines.append(
            "| {variant} | {accuracy} | {precision} | {recall} | "
            "{f1} | {roc_auc} |".format(**entry)
        )
    return "\n".join(lines)


def run(data_dir: Path, model_dir: Path) -> Dict[str, Any]:
    """Execute every ablation variant and persist the results."""
    test_rows = load_jsonl(data_dir / "test.jsonl")
    train_rows = load_jsonl(data_dir / "train.jsonl")
    medians = _training_medians(train_rows)
    LOGGER.info("Evaluating %d ablation variants", 7)

    classifier = MLClassifier(model_dir)
    classifier.load_models()
    engine = FusionEngine()

    variants: List[tuple[str, List[Dict[str, Any]]]] = []

    rules_records = [
        make_record(row, run_rules(row, engine)) for row in test_rows
    ]
    variants.append(("rules_only", rules_records))

    ml_records = [
        make_record(row, run_ml(row, classifier)) for row in test_rows
    ]
    variants.append(("ml_only", ml_records))

    hybrid_records = [
        make_record(row, run_hybrid(row, classifier, engine))
        for row in test_rows
    ]
    variants.append(("hybrid", hybrid_records))

    for source in ABLATION_SOURCES:
        records = [
            make_record(
                row, run_hybrid(_masked_row(row, source, medians), classifier, engine)
            )
            for row in test_rows
        ]
        variants.append((f"hybrid_minus_{source}", records))

    results: List[Dict[str, Any]] = []
    for name, records in variants:
        payload = build_result(name, records)
        entry = {"variant": name, **_f1_summary(payload)}
        results.append(entry)
        LOGGER.info(
            "%-22s F1=%.4f precision=%.4f recall=%.4f roc_auc=%s",
            name,
            entry["f1"],
            entry["precision"],
            entry["recall"],
            entry["roc_auc"],
        )

    markdown = _markdown_table(results)
    output = {
        "study": "source_removal_ablation",
        "n_samples": len(test_rows),
        "results": results,
        "markdown": markdown,
    }
    save_result(data_dir / RESULTS_FILENAME, output)
    return output


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the disruption-source ablation study.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Dataset directory (default: data/disruption_detection).",
    )
    parser.add_argument(
        "--model-dir",
        default=str(MODEL_DIR),
        help="Model directory (default: model_files).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    output = run(Path(args.data_dir), Path(args.model_dir))
    print(output["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())