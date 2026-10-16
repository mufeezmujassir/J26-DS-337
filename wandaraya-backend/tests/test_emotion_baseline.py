"""Pytest suite for TF-IDF Emotion Baseline (WANDARAYA Component 3 Step 5)."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from src.emotion.baseline import (
    DEFAULT_GOEMOTIONS_LABELS,
    binarize_labels,
    evaluate_model,
    load_config,
    set_seed,
)

REPORT_JSON_PATH = Path("reports/baseline_emotion_results.json")
CONFIG_PATH = Path("configs/config.yaml")


def test_config_file_exists_and_valid() -> None:
    """Verify that configs/config.yaml exists and contains all required parameters."""
    assert CONFIG_PATH.is_file(), f"Missing config file at {CONFIG_PATH}"
    config = load_config(CONFIG_PATH)

    assert "seed" in config, "Seed missing from config"
    assert "emotion_baseline" in config, "emotion_baseline section missing from config"

    eb = config["emotion_baseline"]
    assert "dataset" in eb
    assert "vectorizer" in eb
    assert "classifier" in eb
    assert "threshold_tuning" in eb
    assert "paths" in eb


def test_binarize_labels() -> None:
    """Test converting raw label index lists into binary indicator matrix."""
    raw = [[0, 2], [27], []]
    matrix = binarize_labels(raw, num_classes=28)

    assert matrix.shape == (3, 28)
    assert matrix[0, 0] == 1
    assert matrix[0, 2] == 1
    assert matrix[0, 1] == 0
    assert matrix[1, 27] == 1
    assert matrix[2].sum() == 0


def test_evaluate_model_unit() -> None:
    """Test evaluation logic with synthetic predictions."""
    labels = ["joy", "sadness", "neutral"]
    y_true = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ])
    y_pred = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 1, 0],
    ])

    metrics = evaluate_model(y_true, y_pred, labels)

    expected_keys = [
        "subset_accuracy",
        "micro_precision",
        "micro_recall",
        "micro_f1",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
        "per_class",
    ]
    for key in expected_keys:
        assert key in metrics, f"Missing metric key: {key}"

    assert len(metrics["per_class"]) == 3
    for lbl in labels:
        assert "precision" in metrics["per_class"][lbl]
        assert "recall" in metrics["per_class"][lbl]
        assert "f1" in metrics["per_class"][lbl]
        assert "support" in metrics["per_class"][lbl]


def test_baseline_results_json_schema() -> None:
    """Verify that reports/baseline_emotion_results.json has all required keys and valid schema."""
    if not REPORT_JSON_PATH.is_file():
        pytest.skip(
            f"{REPORT_JSON_PATH} not found. Run 'python src/emotion/run_baseline.py' first."
        )

    with open(REPORT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Top-level keys
    required_top_keys = ["threshold", "config", "seed", "test_metrics", "validation_macro_f1"]
    for key in required_top_keys:
        assert key in data, f"Missing top-level key '{key}' in {REPORT_JSON_PATH}"

    assert isinstance(data["seed"], int), "Seed must be an integer"
    assert isinstance(data["threshold"], (float, int)), "Threshold must be numeric"
    assert 0.0 < data["threshold"] < 1.0, f"Threshold {data['threshold']} out of expected range (0, 1)"

    # 2. Config section
    assert "vectorizer" in data["config"]
    assert "classifier" in data["config"]

    # 3. Test metrics section
    tm = data["test_metrics"]
    required_metric_keys = [
        "subset_accuracy",
        "micro_precision",
        "micro_recall",
        "micro_f1",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
        "per_class",
    ]
    for m_key in required_metric_keys:
        assert m_key in tm, f"Missing metric key '{m_key}' in test_metrics"
        if m_key != "per_class":
            assert isinstance(tm[m_key], (float, int)), f"{m_key} must be numeric"

    # 4. Per-class metrics
    per_class = tm["per_class"]
    assert len(per_class) == 28, f"Expected 28 classes in per_class, got {len(per_class)}"

    for class_name in DEFAULT_GOEMOTIONS_LABELS:
        assert class_name in per_class, f"Missing class '{class_name}' in per_class"
        c_data = per_class[class_name]
        for field in ("precision", "recall", "f1", "support"):
            assert field in c_data, f"Class '{class_name}' missing '{field}'"
            assert isinstance(c_data[field], (float, int)), f"{class_name}.{field} must be numeric"
