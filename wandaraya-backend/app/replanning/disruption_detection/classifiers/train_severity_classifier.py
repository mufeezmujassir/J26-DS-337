"""Train the Random Forest disruption-severity classifier."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Allow direct script execution as well as module import.
if __package__ in (None, ""):  # pragma: no cover - script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import (  # noqa: E402
    RandomizedSearchCV,
    cross_val_score,
    train_test_split,
)

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    FEATURE_NAMES,
    LABEL_DISRUPTION,
    MODEL_DIR,
    SEVERITY_LEVELS,
    feature_matrix,
    load_jsonl,
)

LOGGER = logging.getLogger("train_severity_classifier")

MODEL_FILENAME = "severity_classifier.pkl"
RESULTS_FILENAME = "results_train_severity.json"

RANDOM_STATE = 42
DEFAULT_DEV_SIZE = 0.2
N_ITER = 30

PARAM_DISTRIBUTIONS: Dict[str, List[Any]] = {
    "n_estimators": [100, 200, 300],
    "max_depth": [5, 10, 15, None],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf": [1, 2, 4],
    "max_features": ["sqrt", "log2"],
}


def _disruption_matrix(
    rows: List[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the feature matrix and severity labels for disruption rows."""
    disruptions = [
        row for row in rows if row.get("label") == LABEL_DISRUPTION
    ]
    features = np.asarray(feature_matrix(disruptions), dtype=float)
    labels = np.asarray(
        [str(row.get("severity", SEVERITY_LEVELS[0])) for row in disruptions]
    )
    return features, labels


def _score(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """Compute the standard multi-class metric bundle."""
    labels = list(SEVERITY_LEVELS)
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        digits=4,
        zero_division=0,
        output_dict=True,
    )
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(
            float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            4,
        ),
        "weighted_f1": round(
            float(
                f1_score(y_true, y_pred, average="weighted", zero_division=0)
            ),
            4,
        ),
        "labels": labels,
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=labels
        ).tolist(),
        "per_class": {
            level: {
                "precision": round(report[level]["precision"], 4),
                "recall": round(report[level]["recall"], 4),
                "f1": round(report[level]["f1-score"], 4),
                "support": int(report[level]["support"]),
            }
            for level in labels
        },
    }


def train(
    data_dir: Path,
    model_dir: Path,
    seed: int = RANDOM_STATE,
    dev_size: float = DEFAULT_DEV_SIZE,
    n_iter: int = N_ITER,
) -> Dict[str, Any]:
    """Run the full severity-classifier training pipeline."""
    LOGGER.info("Loading training data from %s", data_dir / "train.jsonl")
    rows = load_jsonl(data_dir / "train.jsonl")
    X, y = _disruption_matrix(rows)
    LOGGER.info(
        "Loaded %d disruption rows with %d features", X.shape[0], X.shape[1]
    )

    X_train, X_dev, y_train, y_dev = train_test_split(
        X, y, test_size=dev_size, random_state=seed, stratify=y
    )
    LOGGER.info(
        "Split train=%d dev=%d (stratified)", len(y_train), len(y_dev)
    )

    # Baseline RandomForest.
    baseline = RandomForestClassifier(
        class_weight="balanced", random_state=seed
    )
    baseline.fit(X_train, y_train)
    baseline_metrics = _score(y_dev, baseline.predict(X_dev))
    LOGGER.info(
        "Baseline RF: acc=%.4f macro_f1=%.4f",
        baseline_metrics["accuracy"],
        baseline_metrics["macro_f1"],
    )

    # Randomised hyper-parameter search.
    search = RandomizedSearchCV(
        RandomForestClassifier(class_weight="balanced", random_state=seed),
        param_distributions=PARAM_DISTRIBUTIONS,
        n_iter=n_iter,
        cv=5,
        scoring="f1_macro",
        random_state=seed,
        n_jobs=-1,
    )
    search.fit(X_train, y_train)
    LOGGER.info(
        "Best params: %s (cv macro-F1=%.4f)",
        search.best_params_,
        search.best_score_,
    )

    # Cross-validate the best estimator.
    cv_scores = cross_val_score(
        search.best_estimator_,
        X_train,
        y_train,
        cv=5,
        scoring="f1_macro",
    )
    LOGGER.info(
        "Best estimator 5-fold macro-F1: mean=%.4f std=%.4f",
        cv_scores.mean(),
        cv_scores.std(),
    )

    # Retrain on the full disruption training split.
    final_model = RandomForestClassifier(
        class_weight="balanced",
        random_state=seed,
        **search.best_params_,
    )
    final_model.fit(X, y)

    # Evaluate on the committed dev disruptions.
    dev_rows = load_jsonl(data_dir / "dev.jsonl")
    X_eval, y_eval = _disruption_matrix(dev_rows)
    eval_pred = final_model.predict(X_eval)
    dev_metrics = _score(y_eval, eval_pred)
    LOGGER.info(
        "Final model on dev: acc=%.4f macro_f1=%.4f",
        dev_metrics["accuracy"],
        dev_metrics["macro_f1"],
    )
    for level in SEVERITY_LEVELS:
        metrics = dev_metrics["per_class"][level]
        LOGGER.info(
            "  %-4s precision=%.4f recall=%.4f f1=%.4f support=%d",
            level,
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
            metrics["support"],
        )

    # Persist model and metrics.
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, model_dir / MODEL_FILENAME)
    LOGGER.info("Saved model to %s", model_dir / MODEL_FILENAME)

    importances = {
        name: round(float(value), 6)
        for name, value in zip(
            FEATURE_NAMES, final_model.feature_importances_
        )
    }
    LOGGER.info("Feature importance (descending):")
    for name, value in sorted(
        importances.items(), key=lambda item: item[1], reverse=True
    ):
        LOGGER.info("  %-26s %.6f", name, value)

    results: Dict[str, Any] = {
        "model": "RandomForestClassifier",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_state": seed,
        "feature_names": list(FEATURE_NAMES),
        "severity_levels": list(SEVERITY_LEVELS),
        "best_params": search.best_params_,
        "best_cv_macro_f1": round(float(search.best_score_), 4),
        "cv_macro_f1_scores": [round(float(value), 4) for value in cv_scores],
        "cv_macro_f1_mean": round(float(cv_scores.mean()), 4),
        "cv_macro_f1_std": round(float(cv_scores.std()), 4),
        "baseline_metrics": baseline_metrics,
        "dev_metrics": dev_metrics,
        "feature_importance": importances,
    }

    results_path = data_dir / RESULTS_FILENAME
    results_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Saved training metrics to %s", results_path)
    return results


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Train the disruption-severity Random Forest model.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Dataset directory (default: data/disruption_detection).",
    )
    parser.add_argument(
        "--model-dir",
        default=str(MODEL_DIR),
        help="Model output directory (default: model_files).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=RANDOM_STATE,
        help=f"Random seed (default: {RANDOM_STATE}).",
    )
    parser.add_argument(
        "--dev-size",
        type=float,
        default=DEFAULT_DEV_SIZE,
        help=f"Internal dev fraction (default: {DEFAULT_DEV_SIZE}).",
    )
    parser.add_argument(
        "--n-iter",
        type=int,
        default=N_ITER,
        help=f"RandomizedSearchCV iterations (default: {N_ITER}).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point: train the severity classifier."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    train(
        data_dir=Path(args.data_dir),
        model_dir=Path(args.model_dir),
        seed=args.seed,
        dev_size=args.dev_size,
        n_iter=args.n_iter,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())