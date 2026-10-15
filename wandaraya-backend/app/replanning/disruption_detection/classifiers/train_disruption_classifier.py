"""Train the Logistic Regression disruption-presence classifier."""

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
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (  # noqa: E402
    GridSearchCV,
    cross_val_score,
    train_test_split,
)
from sklearn.preprocessing import StandardScaler  # noqa: E402

from app.replanning.disruption_detection.classifiers import (  # noqa: E402
    DATA_DIR,
    FEATURE_NAMES,
    LABEL_DISRUPTION,
    MODEL_DIR,
    feature_matrix,
    load_jsonl,
)

LOGGER = logging.getLogger("train_disruption_classifier")

MODEL_FILENAME = "disruption_classifier.pkl"
SCALER_FILENAME = "disruption_scaler.pkl"
RESULTS_FILENAME = "results_train_disruption.json"

RANDOM_STATE = 42
DEFAULT_DEV_SIZE = 0.2


def _labelled_matrix(
    rows: List[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the feature matrix and binary presence labels for ``rows``."""
    features = np.asarray(feature_matrix(rows), dtype=float)
    labels = np.asarray(
        [1 if row.get("label") == LABEL_DISRUPTION else 0 for row in rows],
        dtype=int,
    )
    return features, labels


def _score(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> Dict[str, Any]:
    """Compute the standard binary classification metric bundle."""
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(
            float(precision_score(y_true, y_pred, zero_division=0)), 4
        ),
        "recall": round(
            float(recall_score(y_true, y_pred, zero_division=0)), 4
        ),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classification_report": classification_report(
            y_true, y_pred, digits=4, zero_division=0, output_dict=True
        ),
    }


def train(
    data_dir: Path,
    model_dir: Path,
    seed: int = RANDOM_STATE,
    dev_size: float = DEFAULT_DEV_SIZE,
) -> Dict[str, Any]:
    """Run the full training pipeline and return the metrics bundle."""
    LOGGER.info("Loading training data from %s", data_dir / "train.jsonl")
    rows = load_jsonl(data_dir / "train.jsonl")
    X, y = _labelled_matrix(rows)
    LOGGER.info("Loaded %d rows with %d features", X.shape[0], X.shape[1])

    X_train, X_dev, y_train, y_dev = train_test_split(
        X, y, test_size=dev_size, random_state=seed, stratify=y
    )
    LOGGER.info(
        "Split train=%d dev=%d (stratified)", len(y_train), len(y_dev)
    )

    # Scale on the training portion only to avoid leakage.
    scaler = StandardScaler().fit(X_train)
    X_train_scaled = scaler.transform(X_train)
    X_dev_scaled = scaler.transform(X_dev)

    # Baseline LogisticRegression.
    baseline = LogisticRegression(
        class_weight="balanced", max_iter=1000, random_state=seed
    )
    baseline.fit(X_train_scaled, y_train)
    baseline_metrics = _score(
        y_dev,
        baseline.predict(X_dev_scaled),
        baseline.predict_proba(X_dev_scaled)[:, 1],
    )
    LOGGER.info(
        "Baseline LR: acc=%.4f f1=%.4f roc_auc=%.4f",
        baseline_metrics["accuracy"],
        baseline_metrics["f1"],
        baseline_metrics["roc_auc"],
    )

    # Hyper-parameter search over supported (solver, penalty) combinations.
    # l1 requires liblinear; lbfgs only supports l2.
    param_grid = [
        {
            "solver": ["liblinear"],
            "penalty": ["l1", "l2"],
            "C": [0.01, 0.1, 1, 10, 100],
        },
        {
            "solver": ["lbfgs"],
            "penalty": ["l2"],
            "C": [0.01, 0.1, 1, 10, 100],
        },
    ]
    search = GridSearchCV(
        LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=seed
        ),
        param_grid=param_grid,
        cv=5,
        scoring="f1",
        n_jobs=-1,
        error_score=0.0,
    )
    search.fit(X_train_scaled, y_train)
    LOGGER.info("Best params: %s (cv f1=%.4f)", search.best_params_, search.best_score_)

    # Cross-validate the best estimator.
    cv_scores = cross_val_score(
        search.best_estimator_,
        X_train_scaled,
        y_train,
        cv=5,
        scoring="f1",
    )
    LOGGER.info(
        "Best estimator 5-fold F1: mean=%.4f std=%.4f",
        cv_scores.mean(),
        cv_scores.std(),
    )

    # Retrain on the full training split.
    final_scaler = StandardScaler().fit(X)
    X_scaled = final_scaler.transform(X)

    final_model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=seed,
        **search.best_params_,
    )
    final_model.fit(X_scaled, y)

    # Evaluate on the committed dev split.
    dev_rows = load_jsonl(data_dir / "dev.jsonl")
    X_eval, y_eval = _labelled_matrix(dev_rows)
    X_eval_scaled = final_scaler.transform(X_eval)
    eval_prob = final_model.predict_proba(X_eval_scaled)[:, 1]
    eval_pred = final_model.predict(X_eval_scaled)
    dev_metrics = _score(y_eval, eval_pred, eval_prob)
    LOGGER.info(
        "Final model on dev: acc=%.4f precision=%.4f recall=%.4f "
        "f1=%.4f roc_auc=%.4f",
        dev_metrics["accuracy"],
        dev_metrics["precision"],
        dev_metrics["recall"],
        dev_metrics["f1"],
        dev_metrics["roc_auc"],
    )

    # Persist model, scaler, and metrics.
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, model_dir / MODEL_FILENAME)
    joblib.dump(final_scaler, model_dir / SCALER_FILENAME)
    LOGGER.info("Saved model to %s", model_dir / MODEL_FILENAME)
    LOGGER.info("Saved scaler to %s", model_dir / SCALER_FILENAME)

    coefficients = {
        name: round(float(value), 6)
        for name, value in zip(FEATURE_NAMES, final_model.coef_[0])
    }

    results: Dict[str, Any] = {
        "model": "LogisticRegression",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_state": seed,
        "feature_names": list(FEATURE_NAMES),
        "best_params": search.best_params_,
        "best_cv_f1": round(float(search.best_score_), 4),
        "cv_f1_scores": [round(float(value), 4) for value in cv_scores],
        "cv_f1_mean": round(float(cv_scores.mean()), 4),
        "cv_f1_std": round(float(cv_scores.std()), 4),
        "baseline_metrics": baseline_metrics,
        "dev_metrics": dev_metrics,
        "coefficients": coefficients,
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
        description="Train the disruption-presence Logistic Regression model.",
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
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """Entry point: train the presence classifier."""
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())