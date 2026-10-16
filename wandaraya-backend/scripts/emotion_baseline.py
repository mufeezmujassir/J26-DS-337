"""TF-IDF + OneVsRest Logistic Regression baseline for GoEmotions classification.

Part of WANDARAYA Component 3: Emotional Intelligence & Group Decision Agent.
Evaluates multi-label emotion classification across all 28 classes
(27 GoEmotions categories + neutral) with global threshold tuning.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple

from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)
from sklearn.multiclass import OneVsRestClassifier
import yaml

DATA_DIR = Path("data/group_decision")
REPORTS_DIR = DATA_DIR / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"


# Standard 28 GoEmotions simplified labels
DEFAULT_GOEMOTIONS_LABELS: list[str] = [
    "admiration",
    "amusement",
    "anger",
    "annoyance",
    "approval",
    "caring",
    "confusion",
    "curiosity",
    "desire",
    "disappointment",
    "disapproval",
    "disgust",
    "embarrassment",
    "excitement",
    "fear",
    "gratitude",
    "grief",
    "joy",
    "love",
    "nervousness",
    "optimism",
    "pride",
    "realization",
    "relief",
    "remorse",
    "sadness",
    "surprise",
    "neutral",
]


def set_seed(seed: int = 42) -> None:
    """Set random seed for reproducibility across random, numpy, os, and torch."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


def load_config(config_path: str | Path = "configs/config.yaml") -> dict[str, Any]:
    """Load configuration dictionary from YAML file."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found at: {path.resolve()}")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def binarize_labels(
    label_indices_list: list[list[int]],
    num_classes: int = 28,
) -> np.ndarray:
    """Convert a list of label index lists into a binary multi-label indicator matrix."""
    matrix = np.zeros((len(label_indices_list), num_classes), dtype=np.int32)
    for row_idx, labels in enumerate(label_indices_list):
        for lbl in labels:
            if 0 <= lbl < num_classes:
                matrix[row_idx, lbl] = 1
    return matrix


def load_goemotions_splits(
    hf_path: str = "google-research-datasets/go_emotions",
    hf_fallback_path: str = "go_emotions",
    config_name: str = "simplified",
    num_classes: int = 28,
) -> tuple[dict[str, list[str]], dict[str, np.ndarray], list[str]]:
    """Load GoEmotions dataset splits from Hugging Face.

    Returns:
        texts_by_split: Dict mapping split name ('train', 'validation', 'test') to list of texts.
        labels_by_split: Dict mapping split name to binary numpy matrix of shape (N, num_classes).
        label_names: List of all 28 class names in canonical index order.
    """
    raw_dataset = None
    attempted_errors: list[str] = []

    for path in (hf_path, hf_fallback_path):
        try:
            print(f"[*] Loading GoEmotions split from Hugging Face hub: '{path}' ({config_name})...")
            raw_dataset = load_dataset(path, config_name)
            break
        except Exception as exc:
            attempted_errors.append(f"{path}: {exc}")

    if raw_dataset is None:
        error_msg = "\n".join(attempted_errors)
        raise RuntimeError(f"Failed to load GoEmotions dataset. Errors:\n{error_msg}")

    # Extract label names
    label_feature = raw_dataset["train"].features.get("labels")
    if (
        label_feature
        and hasattr(label_feature, "feature")
        and hasattr(label_feature.feature, "names")
    ):
        label_names = list(label_feature.feature.names)
    else:
        label_names = list(DEFAULT_GOEMOTIONS_LABELS)

    if len(label_names) != num_classes:
        print(f"[!] Warning: Expected {num_classes} labels, found {len(label_names)}. Using label_names length.")
        num_classes = len(label_names)

    texts_by_split: dict[str, list[str]] = {}
    labels_by_split: dict[str, np.ndarray] = {}

    for split in ("train", "validation", "test"):
        split_data = raw_dataset[split]
        texts = [str(t) for t in split_data["text"]]
        raw_labels = split_data["labels"]
        binary_targets = binarize_labels(raw_labels, num_classes=num_classes)

        texts_by_split[split] = texts
        labels_by_split[split] = binary_targets
        print(f"    Loaded {split} split: {len(texts):,} samples (multi-label matrix: {binary_targets.shape})")

    return texts_by_split, labels_by_split, label_names


def train_vectorizer_and_classifier(
    train_texts: list[str],
    y_train: np.ndarray,
    val_texts: list[str],
    test_texts: list[str],
    vectorizer_cfg: dict[str, Any],
    classifier_cfg: dict[str, Any],
    seed: int = 42,
) -> tuple[TfidfVectorizer, OneVsRestClassifier, Any, Any, Any]:
    """Fit TF-IDF on train texts only, transform all splits, and fit OneVsRest Logistic Regression."""
    ngram_range = tuple(vectorizer_cfg.get("ngram_range", [1, 2]))
    max_features = vectorizer_cfg.get("max_features", 50000)
    sublinear_tf = vectorizer_cfg.get("sublinear_tf", True)

    print(f"[*] Fitting TfidfVectorizer (ngram_range={ngram_range}, max_features={max_features}, sublinear_tf={sublinear_tf})...")
    vectorizer = TfidfVectorizer(
        ngram_range=ngram_range,
        max_features=max_features,
        sublinear_tf=sublinear_tf,
    )

    X_train_vec = vectorizer.fit_transform(train_texts)
    X_val_vec = vectorizer.transform(val_texts)
    X_test_vec = vectorizer.transform(test_texts)
    print(f"    TF-IDF vocabulary size: {len(vectorizer.vocabulary_):,} features")

    solver = classifier_cfg.get("solver", "lbfgs")
    max_iter = classifier_cfg.get("max_iter", 1000)
    class_weight = classifier_cfg.get("class_weight", "balanced")
    n_jobs = classifier_cfg.get("n_jobs", -1)

    print(f"[*] Training OneVsRestClassifier(LogisticRegression(max_iter={max_iter}, class_weight='{class_weight}')) on train split...")
    base_lr = LogisticRegression(
        solver=solver,
        max_iter=max_iter,
        class_weight=class_weight,
        random_state=seed,
    )
    clf = OneVsRestClassifier(base_lr, n_jobs=n_jobs)
    clf.fit(X_train_vec, y_train)
    print(f"    Fitted {len(clf.estimators_)} binary estimators.")

    return vectorizer, clf, X_train_vec, X_val_vec, X_test_vec


def tune_global_threshold(
    model: OneVsRestClassifier,
    X_val_vec: Any,
    y_val: np.ndarray,
    min_threshold: float = 0.05,
    max_threshold: float = 0.95,
    step: float = 0.02,
) -> tuple[float, float, dict[float, float]]:
    """Tune a single global decision threshold on the validation set to maximize macro-F1.

    Returns:
        best_threshold: Tuned threshold value maximizing validation macro-F1.
        best_macro_f1: Peak validation macro-F1 achieved.
        threshold_f1_curve: Dictionary of evaluated thresholds and their macro-F1 scores.
    """
    print(f"[*] Tuning global threshold on validation split (range=[{min_threshold}, {max_threshold}], step={step})...")
    val_probs = model.predict_proba(X_val_vec)

    thresholds = np.arange(min_threshold, max_threshold + (step / 2.0), step)
    best_threshold = 0.5
    best_macro_f1 = -1.0
    threshold_f1_curve: dict[float, float] = {}

    for t in thresholds:
        t_val = round(float(t), 4)
        y_val_pred = (val_probs >= t_val).astype(int)
        score = float(f1_score(y_val, y_val_pred, average="macro", zero_division=0))
        threshold_f1_curve[t_val] = round(score, 5)

        if score > best_macro_f1:
            best_macro_f1 = score
            best_threshold = t_val

    print(f"    Optimal validation threshold: {best_threshold:.4f} (Validation Macro-F1: {best_macro_f1:.4f})")
    return best_threshold, best_macro_f1, threshold_f1_curve


def evaluate_model(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    label_names: list[str],
) -> dict[str, Any]:
    """Compute comprehensive multi-label evaluation metrics."""
    subset_acc = float(accuracy_score(y_true, y_pred))

    micro_p = float(precision_score(y_true, y_pred, average="micro", zero_division=0))
    micro_r = float(recall_score(y_true, y_pred, average="micro", zero_division=0))
    micro_f1 = float(f1_score(y_true, y_pred, average="micro", zero_division=0))

    macro_p = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    macro_r = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    weighted_p = float(precision_score(y_true, y_pred, average="weighted", zero_division=0))
    weighted_r = float(recall_score(y_true, y_pred, average="weighted", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    prec_per_class, rec_per_class, f1_per_class, supp_per_class = precision_recall_fscore_support(
        y_true, y_pred, average=None, zero_division=0
    )

    per_class: dict[str, dict[str, float | int]] = {}
    for idx, name in enumerate(label_names):
        per_class[name] = {
            "precision": round(float(prec_per_class[idx]), 4),
            "recall": round(float(rec_per_class[idx]), 4),
            "f1": round(float(f1_per_class[idx]), 4),
            "support": int(supp_per_class[idx]),
        }

    return {
        "subset_accuracy": round(subset_acc, 4),
        "micro_precision": round(micro_p, 4),
        "micro_recall": round(micro_r, 4),
        "micro_f1": round(micro_f1, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_precision": round(weighted_p, 4),
        "weighted_recall": round(weighted_r, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_class": per_class,
    }


def plot_per_class_f1(
    per_class_metrics: dict[str, dict[str, float | int]],
    macro_f1: float,
    output_path: str | Path,
) -> None:
    """Plot and save a styled horizontal bar chart of per-class test F1 scores."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    classes = list(per_class_metrics.keys())
    f1_scores = [float(per_class_metrics[c]["f1"]) for c in classes]

    # Sort descending by F1 score for readability
    sorted_pairs = sorted(zip(classes, f1_scores), key=lambda x: x[1], reverse=False)
    sorted_classes = [p[0] for p in sorted_pairs]
    sorted_scores = [p[1] for p in sorted_pairs]

    plt.figure(figsize=(10, 12), dpi=300)
    bars = plt.barh(sorted_classes, sorted_scores, color="#1f77b4", edgecolor="#0e4b75", height=0.7)

    # Value labels on bars
    for bar in bars:
        width = bar.get_width()
        plt.text(
            width + 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{width:.3f}",
            va="center",
            ha="left",
            fontsize=9,
            color="#222222",
        )

    # Macro-F1 benchmark reference line
    plt.axvline(
        macro_f1,
        color="#d62728",
        linestyle="--",
        linewidth=1.8,
        label=f"Macro-F1 Benchmark ({macro_f1:.3f})",
    )

    plt.title("GoEmotions Multi-Label Baseline: Per-Class F1 Score (Test Split)", fontsize=14, pad=15)
    plt.xlabel("F1 Score", fontsize=11, labelpad=10)
    plt.ylabel("Emotion Category", fontsize=11, labelpad=10)
    plt.xlim(0.0, max(max(sorted_scores) + 0.08, 1.0))
    plt.grid(axis="x", linestyle=":", alpha=0.6)
    plt.legend(loc="lower right", frameon=True)
    plt.tight_layout()

    plt.savefig(out, dpi=300)
    plt.close()
    print(f"[*] Per-class F1 bar chart saved to: {out.resolve()}")


def save_results_json(results: dict[str, Any], output_path: str | Path) -> None:
    """Serialize results dictionary to formatted JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[*] Evaluation results saved to: {out.resolve()}")


def run_emotion_baseline(config_path: str | Path = "configs/config.yaml") -> dict[str, Any]:
    """Execute the end-to-end TF-IDF emotion classification baseline pipeline."""
    config = load_config(config_path)
    seed = int(config.get("seed", 42))
    set_seed(seed)

    baseline_cfg = config.get("emotion_baseline", {})
    dataset_cfg = baseline_cfg.get("dataset", {})
    vectorizer_cfg = baseline_cfg.get("vectorizer", {})
    classifier_cfg = baseline_cfg.get("classifier", {})
    tuning_cfg = baseline_cfg.get("threshold_tuning", {})
    paths_cfg = baseline_cfg.get("paths", {})

    hf_path = dataset_cfg.get("hf_path", "google-research-datasets/go_emotions")
    hf_fallback_path = dataset_cfg.get("hf_fallback_path", "go_emotions")
    config_name = dataset_cfg.get("config_name", "simplified")
    num_classes = int(dataset_cfg.get("num_classes", 28))

    # 1. Load data
    texts_by_split, labels_by_split, label_names = load_goemotions_splits(
        hf_path=hf_path,
        hf_fallback_path=hf_fallback_path,
        config_name=config_name,
        num_classes=num_classes,
    )

    # 2. Train Vectorizer & OneVsRest Classifier
    vectorizer, clf, X_train_vec, X_val_vec, X_test_vec = train_vectorizer_and_classifier(
        train_texts=texts_by_split["train"],
        y_train=labels_by_split["train"],
        val_texts=texts_by_split["validation"],
        test_texts=texts_by_split["test"],
        vectorizer_cfg=vectorizer_cfg,
        classifier_cfg=classifier_cfg,
        seed=seed,
    )

    # 3. Global threshold tuning on validation split
    min_t = float(tuning_cfg.get("min_threshold", 0.05))
    max_t = float(tuning_cfg.get("max_threshold", 0.95))
    step_t = float(tuning_cfg.get("step", 0.02))

    best_threshold, val_macro_f1, _ = tune_global_threshold(
        model=clf,
        X_val_vec=X_val_vec,
        y_val=labels_by_split["validation"],
        min_threshold=min_t,
        max_threshold=max_t,
        step=step_t,
    )

    # 4. Evaluate once on test split with tuned threshold
    print(f"[*] Evaluating on test split with global threshold {best_threshold:.4f}...")
    test_probs = clf.predict_proba(X_test_vec)
    y_test_pred = (test_probs >= best_threshold).astype(int)

    test_metrics = evaluate_model(
        y_true=labels_by_split["test"],
        y_pred=y_test_pred,
        label_names=label_names,
    )

    # 5. Build results payload
    results_payload = {
        "seed": seed,
        "threshold": best_threshold,
        "validation_macro_f1": round(val_macro_f1, 4),
        "config": {
            "dataset": dataset_cfg,
            "vectorizer": vectorizer_cfg,
            "classifier": classifier_cfg,
            "threshold_tuning": tuning_cfg,
        },
        "test_metrics": test_metrics,
    }

    # 6. Save outputs
   
    json_path = paths_cfg.get("results_json", REPORTS_DIR / "baseline_emotion_results.json")
    figure_path = paths_cfg.get("f1_figure", FIGURES_DIR / "baseline_emotion_f1.png")

    save_results_json(results_payload, json_path)
    plot_per_class_f1(test_metrics["per_class"], test_metrics["macro_f1"], figure_path)

    return results_payload
