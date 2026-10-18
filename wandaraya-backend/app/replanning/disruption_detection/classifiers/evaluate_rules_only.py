"""Evaluate the rule-based detector alone on the frozen test split."""

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
    load_jsonl,
)
from app.replanning.disruption_detection.classifiers._evaluation import (  # noqa: E402
    build_result,
    make_record,
    run_rules,
    save_result,
    summary_table,
)
from app.replanning.disruption_detection.fusion import FusionEngine  # noqa: E402

LOGGER = logging.getLogger("evaluate_rules_only")
RESULTS_FILENAME = "results_rules_only.json"


def evaluate(data_dir: Path) -> Dict:
    """Evaluate the rule-based detector and return the result payload."""
    rows = load_jsonl(data_dir / "test.jsonl")
    LOGGER.info("Evaluating rules-only on %d test rows", len(rows))

    engine = FusionEngine()
    records = []
    for row in rows:
        prediction = run_rules(row, engine)
        records.append(make_record(row, prediction))

    payload = build_result("rules_only", records)
    out_path = save_result(data_dir / RESULTS_FILENAME, payload)
    LOGGER.info("Rules-only results written to %s", out_path)
    return payload


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate the rule-based disruption detector.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Dataset directory (default: data/disruption_detection).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    payload = evaluate(Path(args.data_dir))
    print(summary_table(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())