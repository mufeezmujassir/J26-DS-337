"""Train the single production Random Forest intent-preservation classifier."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, cross_val_score  # noqa: E402

from app.replanning.dynamic_replanning.classifiers import (  # noqa: E402
    FEATURE_NAMES,
    MODEL_FILENAME,
    MODEL_DIR,
    PROCESSED_DIR,
    LABEL_BROKEN,
    LABEL_PRESERVED,
    feature_matrix,
    label_value,
    load_jsonl,
)

LOGGER = logging.getLogger("train_intent_classifier")

RESULTS_FILENAME = "results_train_intent.json"
RANDOM_STATE = 42


def _labels(rows: List[Dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [1 if label_value(r) == LABEL_PRESERVED else 0 for r in rows],
        dtype=int,
    )


def _score(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> Dict[str, Any]:
    try:
        roc_auc = roc_auc_score(y_true, y_prob)
    except Exception:
        roc_auc = None
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc), 4) if roc_auc is not None else None,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classification_report": classification_report(
            y_true, y_pred, digits=4, zero_division=0, output_dict=True
        ),
    }


def train(
    data_dir: Path,
    model_dir: Path,
    seed: int = RANDOM_STATE,
) -> Dict[str, Any]:
    LOGGER.info("Loading train.jsonl from %s", data_dir / "train.jsonl")
    train_rows = load_jsonl(data_dir / "train.jsonl")
    X_train = np.asarray(feature_matrix(train_rows), dtype=float)
    y_train = _labels(train_rows)

    param_dist = {
        "n_estimators": [100, 200, 300],
        "max_depth": [5, 10, 15, None],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf": [1, 2, 4],
        "max_features": ["sqrt", "log2"],
        "class_weight": ["balanced"],
    }
    search = RandomizedSearchCV(
        RandomForestClassifier(random_state=seed),
        param_distributions=param_dist,
        n_iter=30,
        cv=5,
        scoring="f1",
        n_jobs=-1,
        random_state=seed,
    )
    search.fit(X_train, y_train)
    LOGGER.info("Best params: %s (cv f1=%.4f)", search.best_params_, search.best_score_)

    cv_scores = cross_val_score(
        search.best_estimator_,
        X_train,
        y_train,
        cv=5,
        scoring="f1",
    )
    LOGGER.info(
        "5-fold F1: mean=%.4f std=%.4f",
        float(cv_scores.mean()),
        float(cv_scores.std()),
    )

    # Retrain on full train
    X_full = X_train
    y_full = y_train
    params = dict(search.best_params_)
    params.setdefault("class_weight", "balanced")
    final_model = RandomForestClassifier(random_state=seed, **params)
    final_model.fit(X_full, y_full)

    # Evaluate on dev
    dev_rows = load_jsonl(data_dir / "dev.jsonl")
    X_dev = np.asarray(feature_matrix(dev_rows), dtype=float)
    y_dev = _labels(dev_rows)
    y_pred = final_model.predict(X_dev)
    y_prob = final_model.predict_proba(X_dev)[:, 1]
    dev_metrics = _score(y_dev, y_pred, y_prob)
    LOGGER.info(
        "Dev: acc=%.4f prec=%.4f rec=%.4f f1=%.4f roc_auc=%s",
        dev_metrics["accuracy"],
        dev_metrics["precision"],
        dev_metrics["recall"],
        dev_metrics["f1"],
        dev_metrics["roc_auc"],
    )

    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, model_dir / MODEL_FILENAME)
    LOGGER.info("Saved model to %s", model_dir / MODEL_FILENAME)

    importances = {
        name: round(float(val), 6)
        for name, val in zip(FEATURE_NAMES, final_model.feature_importances_)
    }
    top10 = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]

    results: Dict[str, Any] = {
        "model": "RandomForestClassifier",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_state": seed,
        "feature_names": list(FEATURE_NAMES),
        "best_params": search.best_params_,
        "best_cv_f1": round(float(search.best_score_), 4),
        "cv_f1_scores": [round(float(v), 4) for v in cv_scores],
        "cv_f1_mean": round(float(cv_scores.mean()), 4),
        "cv_f1_std": round(float(cv_scores.std()), 4),
        "dev_metrics": dev_metrics,
        "feature_importances": importances,
        "top10_feature_importances": dict(top10),
    }
    (data_dir / RESULTS_FILENAME).write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Saved training metrics to %s", data_dir / RESULTS_FILENAME)
    return results


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Random Forest intent classifier.")
    parser.add_argument("--data-dir", default=str(PROCESSED_DIR), help="Dataset directory.")
    parser.add_argument("--model-dir", default=str(MODEL_DIR), help="Model directory.")
    parser.add_argument("--seed", type=int, default=RANDOM_STATE, help="Random seed.")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    train(Path(args.data_dir), Path(args.model_dir), seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
