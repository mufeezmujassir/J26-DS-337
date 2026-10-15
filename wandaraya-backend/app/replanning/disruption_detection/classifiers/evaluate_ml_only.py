"""Evaluate the supervised ML classifiers alone on the frozen test split."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    MODEL_DIR,
    load_jsonl,
)
from app.replanning.disruption_detection.classifiers._evaluation import (  # noqa: E402
    build_result,
    make_record,
    run_ml,
    save_result,
    summary_table,
)
from app.replanning.disruption_detection.ml_classifier import (  # noqa: E402
    MLClassifier,
)

LOGGER = logging.getLogger("evaluate_ml_only")
RESULTS_FILENAME = "results_ml_only.json"


def evaluate(data_dir: Path, model_dir: Path) -> Dict:
    """Evaluate the ML classifiers and return the result payload."""
    rows = load_jsonl(data_dir / "test.jsonl")
    LOGGER.info("Evaluating ML-only on %d test rows", len(rows))

    classifier = MLClassifier(model_dir)
    classifier.load_models()

    records = []
    for row in rows:
        prediction = run_ml(row, classifier)
        records.append(make_record(row, prediction))

    payload = build_result("ml_only", records)
    out_path = save_result(data_dir / RESULTS_FILENAME, payload)
    LOGGER.info("ML-only results written to %s", out_path)
    return payload


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate the ML disruption classifiers.",
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
    payload = evaluate(Path(args.data_dir), Path(args.model_dir))
    print(summary_table(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())