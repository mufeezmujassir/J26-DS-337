"""Measure per-sample inference latency for the intent-preservation variants."""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.replanning.dynamic_replanning.classifiers import (  # noqa: E402
    MODEL_DIR,
    PROCESSED_DIR,
    load_jsonl,
)
from app.replanning.dynamic_replanning.classifiers._evaluation import (  # noqa: E402
    run_hybrid,
    run_ml,
    run_rules,
    save_result,
)
from app.replanning.dynamic_replanning.intent_classifier import (  # noqa: E402
    IntentClassifier,
)

LOGGER = logging.getLogger("measure_latency")
RESULTS_FILENAME = "results_latency.json"
NUM_SAMPLES = 100


def _percentile(values: List[float], percentile: float) -> float:
    """Return the ``percentile`` (0-100) of ``values`` (linear interpolation)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percentile / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _time_predictor(
    name: str, predictor: Callable[[Dict[str, Any]], Any], rows: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Time ``predictor`` over ``rows`` and return a latency summary."""
    # Warm-up to exclude one-off import / lazy-init costs.
    for row in rows[:5]:
        predictor(row)

    timings_ms: List[float] = []
    for row in rows:
        start = time.perf_counter()
        predictor(row)
        timings_ms.append((time.perf_counter() - start) * 1000.0)

    summary = {
        "variant": name,
        "samples": len(timings_ms),
        "mean_ms": round(statistics.fmean(timings_ms), 4),
        "p50_ms": round(_percentile(timings_ms, 50), 4),
        "p95_ms": round(_percentile(timings_ms, 95), 4),
        "p99_ms": round(_percentile(timings_ms, 99), 4),
        "max_ms": round(max(timings_ms), 4),
        "min_ms": round(min(timings_ms), 4),
    }
    LOGGER.info(
        "%-10s mean=%.4fms p50=%.4f p95=%.4f p99=%.4f max=%.4f",
        name,
        summary["mean_ms"],
        summary["p50_ms"],
        summary["p95_ms"],
        summary["p99_ms"],
        summary["max_ms"],
    )
    return summary


def run(
    data_dir: Path, model_dir: Path, num_samples: int = NUM_SAMPLES
) -> Dict[str, Any]:
    """Benchmark the three variants and persist the results."""
    rows = load_jsonl(data_dir / "test.jsonl")[:num_samples]
    LOGGER.info("Benchmarking latency on %d samples", len(rows))

    classifier = IntentClassifier(model_dir)
    classifier.load_model()

    results = [
        _time_predictor("rules_only", lambda row: run_rules(row), rows),
        _time_predictor("ml_only", lambda row: run_ml(row, classifier), rows),
        _time_predictor("hybrid", lambda row: run_hybrid(row, classifier), rows),
    ]

    output = {
        "study": "inference_latency",
        "num_samples": len(rows),
        "results": results,
    }
    save_result(data_dir / RESULTS_FILENAME, output)
    return output


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Measure intent-classifier inference latency.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(PROCESSED_DIR),
        help="Dataset directory (default: data/replanning/intent/processed).",
    )
    parser.add_argument(
        "--model-dir",
        default=str(MODEL_DIR),
        help="Model directory (default: model_files).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=NUM_SAMPLES,
        help=f"Number of samples to time (default: {NUM_SAMPLES}).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    output = run(Path(args.data_dir), Path(args.model_dir), args.samples)
    print(
        "| Variant | mean (ms) | p50 | p95 | p99 | max |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    for entry in output["results"]:
        print(
            "| {variant} | {mean_ms} | {p50_ms} | {p95_ms} | {p99_ms} | "
            "{max_ms} |".format(**entry)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
