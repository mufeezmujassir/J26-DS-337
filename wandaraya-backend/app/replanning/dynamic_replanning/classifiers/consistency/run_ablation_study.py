"""Feature-group removal ablation study for the consistency hybrid on the frozen test split."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import numpy as np  # noqa: E402

from app.replanning.dynamic_replanning.classifiers import load_jsonl  # noqa: E402
from app.replanning.dynamic_replanning.classifiers.consistency import (  # noqa: E402
    CONSISTENCY_MODEL_DIR,
    CONSISTENCY_PROCESSED_DIR,
    FEATURE_NAMES,
)
from app.replanning.dynamic_replanning.classifiers.consistency._evaluation import (  # noqa: E402
    FEATURE_GROUPS,
    build_result,
    make_record,
    run_hybrid,
    run_ml,
    run_rules,
    save_result,
)
from app.replanning.dynamic_replanning.consistency_classifier import (  # noqa: E402
    ConsistencyClassifier,
)

LOGGER = logging.getLogger("run_ablation_study")
RESULTS_FILENAME = "results_consistency_ablation.json"

# Feature groups removed one at a time to build the hybrid_minus_* variants.
ABLATION_GROUPS = tuple(FEATURE_GROUPS.keys())


def _training_medians(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Return the per-feature median over the training rows."""
    medians: Dict[str, float] = {}
    for name in FEATURE_NAMES:
        values = [float(row.get(name, 0.0)) for row in rows]
        medians[name] = float(np.median(values))
    return medians


def _masked_row(
    row: Dict[str, Any], group: str, medians: Dict[str, float]
) -> Dict[str, Any]:
    """Copy ``row`` with all features of ``group`` replaced by medians."""
    masked = dict(row)
    for feature in FEATURE_GROUPS[group]:
        masked[feature] = medians[feature]
    return masked


def _presence_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
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
    LOGGER.info("Evaluating %d ablation variants", 3 + len(ABLATION_GROUPS))

    classifier = ConsistencyClassifier(model_dir)
    classifier.load_model()

    variants: List[Tuple[str, List[Dict[str, Any]]]] = []

    rules_records = [make_record(row, run_rules(row)) for row in test_rows]
    variants.append(("rules_only", rules_records))

    ml_records = [make_record(row, run_ml(row, classifier)) for row in test_rows]
    variants.append(("ml_only", ml_records))

    hybrid_records = [
        make_record(row, run_hybrid(row, classifier)) for row in test_rows
    ]
    variants.append(("hybrid", hybrid_records))

    for group in ABLATION_GROUPS:
        records = [
            make_record(
                row, run_hybrid(_masked_row(row, group, medians), classifier)
            )
            for row in test_rows
        ]
        variants.append((f"hybrid_minus_{group}", records))

    results: List[Dict[str, Any]] = []
    for name, records in variants:
        payload = build_result(name, records)
        entry = {"variant": name, **_presence_summary(payload)}
        results.append(entry)
        LOGGER.info(
            "%-28s F1=%.4f precision=%.4f recall=%.4f roc_auc=%s",
            name,
            entry["f1"],
            entry["precision"],
            entry["recall"],
            entry["roc_auc"],
        )

    markdown = _markdown_table(results)
    output = {
        "study": "feature_group_removal_ablation",
        "n_samples": len(test_rows),
        "feature_groups": {k: list(v) for k, v in FEATURE_GROUPS.items()},
        "results": results,
        "markdown": markdown,
    }
    save_result(data_dir / RESULTS_FILENAME, output)
    return output


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the consistency feature-group ablation study.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(CONSISTENCY_PROCESSED_DIR),
        help="Dataset directory (default: data/replanning/consistency/processed).",
    )
    parser.add_argument(
        "--model-dir",
        default=str(CONSISTENCY_MODEL_DIR),
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
