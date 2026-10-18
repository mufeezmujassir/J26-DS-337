"""Runner script for WANDARAYA Component 3: TF-IDF Emotion Baseline.

Reads hyperparameters, paths, and seed from configs/config.yaml, trains the baseline,
tunes the decision threshold on validation, evaluates on test, prints summary metrics,
and writes results and figures to reports/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure root directory is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# Ensures Python finds companion files in the scripts directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from emotion_baseline import run_emotion_baseline 




def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TF-IDF + Logistic Regression baseline on GoEmotions dataset."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(ROOT_DIR / "configs" / "config.yaml"),
        help="Path to YAML configuration file",
    )
    return parser.parse_args()



def print_summary_table(results: dict) -> None:
    """Print formatted summary metrics table to stdout."""
    metrics = results.get("test_metrics", {})
    threshold = results.get("threshold", 0.5)
    val_macro_f1 = results.get("validation_macro_f1", 0.0)
    seed = results.get("seed", 42)

    print("\n" + "=" * 76)
    print("  WANDARAYA C3 - GOEMOTIONS TF-IDF BASELINE RESULTS (TEST SPLIT)")
    print("=" * 76)
    print(f"  Random Seed                     : {seed}")
    print(f"  Validation Tuned Threshold      : {threshold:.4f}")
    print(f"  Validation Macro-F1             : {val_macro_f1:.4f}")
    print("-" * 76)
    print(f"  Test Subset Accuracy (Exact)    : {metrics.get('subset_accuracy', 0.0):.4f}")
    print(f"  Test Micro Precision / Recall   : {metrics.get('micro_precision', 0.0):.4f} / {metrics.get('micro_recall', 0.0):.4f}")
    print(f"  Test Micro-F1                   : {metrics.get('micro_f1', 0.0):.4f}")
    print(f"  Test Macro Precision / Recall   : {metrics.get('macro_precision', 0.0):.4f} / {metrics.get('macro_recall', 0.0):.4f}")
    print(f"  Test Macro-F1                   : {metrics.get('macro_f1', 0.0):.4f}")
    print(f"  Test Weighted Precision/Recall  : {metrics.get('weighted_precision', 0.0):.4f} / {metrics.get('weighted_recall', 0.0):.4f}")
    print(f"  Test Weighted-F1                : {metrics.get('weighted_f1', 0.0):.4f}")
    print("=" * 76)

    per_class = metrics.get("per_class", {})
    if per_class:
        print("\n" + "-" * 76)
        print(f"  {'Emotion Class':<18} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Support':<8}")
        print("-" * 76)
        for class_name, c_metrics in sorted(per_class.items()):
            p = c_metrics.get("precision", 0.0)
            r = c_metrics.get("recall", 0.0)
            f1 = c_metrics.get("f1", 0.0)
            s = c_metrics.get("support", 0)
            print(f"  {class_name:<18} | {p:<10.4f} | {r:<10.4f} | {f1:<10.4f} | {s:<8}")
        print("-" * 76 + "\n")


def main() -> None:
    args = parse_args()
    print(f"[*] Starting TF-IDF baseline with config: {args.config}")
    results = run_emotion_baseline(config_path=args.config)
    print_summary_table(results)
    print("[SUCCESS] TF-IDF emotion classification baseline run complete.")


if __name__ == "__main__":
    main()
