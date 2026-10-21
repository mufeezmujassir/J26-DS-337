"""Evaluate the rules-only consistency baseline on the frozen test split."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from app.replanning.dynamic_replanning.classifiers import load_jsonl  # noqa: E402
from app.replanning.dynamic_replanning.classifiers.consistency import (  # noqa: E402
    CONSISTENCY_PROCESSED_DIR,
)
from app.replanning.dynamic_replanning.classifiers.consistency._evaluation import (  # noqa: E402
    build_result,
    make_record,
    run_rules,
    save_result,
    summary_table,
)

LOGGER = logging.getLogger("evaluate_rules_only")
RESULTS_FILENAME = "results_consistency_rules_only.json"


def evaluate(data_dir: Path) -> Dict[str, Any]:
    """Evaluate the rules-only baseline and return the result payload."""
    rows = load_jsonl(data_dir / "test.jsonl")
    LOGGER.info("Evaluating rules-only on %d test rows", len(rows))

    records = [make_record(row, run_rules(row)) for row in rows]

    payload = build_result("rules_only", records)
    save_result(data_dir / RESULTS_FILENAME, payload)
    return payload


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate the rules-only consistency baseline.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(CONSISTENCY_PROCESSED_DIR),
        help="Dataset directory (default: data/replanning/consistency/processed).",
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
