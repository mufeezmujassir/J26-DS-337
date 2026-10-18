"""Pytest test suite for RoBERTa emotion predict() module.

Tests output shape, probability ranges [0.0, 1.0], global and per-class
threshold filtering, and edge cases using a mock model and tokenizer
without requiring a GPU or network access.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch
import pytest
import torch

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from test_emotion_baseline import DEFAULT_GOEMOTIONS_LABELS
from app.group_decision.emotion.predict import EmotionPredictor, predict, predict_labels



class DummyModelOutputs:
    """Mock huggingface model output containing logits tensor."""

    def __init__(self, logits: torch.Tensor) -> None:
        self.logits = logits


class DummyEmotionModel(torch.nn.Module):
    """Deterministic mock model returning predictable 28-class logits."""

    def __init__(self, num_classes: int = 28) -> None:
        super().__init__()
        self.num_classes = num_classes

    def forward(self, input_ids: torch.Tensor = None, attention_mask: torch.Tensor = None) -> DummyModelOutputs:
        batch_size = input_ids.shape[0] if input_ids is not None else 1
        # Set logits: class 0 ("admiration") high (+3.0 -> ~0.95), class 17 ("joy") high (+2.5 -> ~0.92)
        # Class 1 ("amusement") low (-4.0 -> ~0.02)
        logits = torch.full((batch_size, self.num_classes), -2.0, dtype=torch.float32)
        logits[:, 0] = 3.0   # admiration -> ~0.9526
        logits[:, 17] = 2.5  # joy -> ~0.9241
        logits[:, 1] = -4.0  # amusement -> ~0.0180
        return DummyModelOutputs(logits)


class DummyTokenizer:
    """Mock tokenizer returning valid PyTorch tensors."""

    def __call__(
        self,
        texts: list[str] | str,
        truncation: bool = True,
        padding: bool = True,
        max_length: int = 64,
        return_tensors: str = "pt",
    ) -> dict[str, torch.Tensor]:
        if isinstance(texts, str):
            text_list = [texts]
        else:
            text_list = list(texts)

        batch_size = len(text_list)
        return {
            "input_ids": torch.ones((batch_size, 16), dtype=torch.long),
            "attention_mask": torch.ones((batch_size, 16), dtype=torch.long),
        }


@pytest.fixture
def dummy_thresholds() -> dict[str, Any]:
    """Standard mock thresholds for testing."""
    per_class = {name: 0.5 for name in DEFAULT_GOEMOTIONS_LABELS}
    # Customize admiration and joy thresholds
    per_class["admiration"] = 0.4
    per_class["joy"] = 0.8
    per_class["amusement"] = 0.5

    return {
        "global_threshold": 0.5,
        "per_class_thresholds": per_class,
        "label_names": list(DEFAULT_GOEMOTIONS_LABELS),
    }


@pytest.fixture
def mock_predictor(dummy_thresholds: dict[str, Any]) -> EmotionPredictor:
    """EmotionPredictor instantiated with mock model and tokenizer on CPU."""
    return EmotionPredictor(
        model=DummyEmotionModel(num_classes=28),
        tokenizer=DummyTokenizer(),
        thresholds_data=dummy_thresholds,
        device="cpu",
    )


def test_predict_probabilities_shape_and_classes(mock_predictor: EmotionPredictor) -> None:
    """Test output length, dictionary keys, and all 28 classes presence."""
    texts = ["I love this trip!", "This is so disappointing.", "Looking forward to it."]
    probs = mock_predictor.predict_probabilities(texts)

    assert isinstance(probs, list)
    assert len(probs) == len(texts), f"Expected {len(texts)} results, got {len(probs)}"

    for item in probs:
        assert isinstance(item, dict)
        assert len(item) == 28, f"Expected 28 classes, got {len(item)}"
        assert set(item.keys()) == set(DEFAULT_GOEMOTIONS_LABELS)


def test_predict_probabilities_range(mock_predictor: EmotionPredictor) -> None:
    """Test that all predicted probabilities lie strictly between 0.0 and 1.0."""
    texts = ["Sample text message 1", "Another message"]
    probs = mock_predictor.predict_probabilities(texts)

    for item in probs:
        for emotion, p_val in item.items():
            assert isinstance(p_val, float)
            assert 0.0 <= p_val <= 1.0, f"Probability for {emotion} is out of bounds: {p_val}"


def test_predict_labels_with_global_threshold(mock_predictor: EmotionPredictor) -> None:
    """Test applying global decision thresholding."""
    texts = ["Test message"]
    labels = mock_predictor.predict_labels(texts, threshold_strategy="global")

    assert isinstance(labels, list)
    assert len(labels) == 1
    pred_emotions = labels[0]
    
    assert "admiration" in pred_emotions
    assert "joy" in pred_emotions
    assert "amusement" not in pred_emotions


def test_predict_labels_with_per_class_threshold(mock_predictor: EmotionPredictor) -> None:
    """Test applying class-specific thresholds."""
    texts = ["Test message"]
    labels = mock_predictor.predict_labels(texts, threshold_strategy="per_class")

    assert isinstance(labels, list)
    pred_emotions = labels[0]
    assert "admiration" in pred_emotions
    assert "joy" in pred_emotions
    assert "amusement" not in pred_emotions


def test_predict_function_end_to_end_mocked(dummy_thresholds: dict[str, Any]) -> None:
    """Test the top-level predict() function with patched AutoModel and AutoTokenizer."""
    texts = ["First message", "Second message"]

    with patch("app.group_decision.emotion.predict.AutoTokenizer.from_pretrained", return_value=DummyTokenizer()), \
         patch("app.group_decision.emotion.predict.AutoModelForSequenceClassification.from_pretrained", return_value=DummyEmotionModel(28)), \
         patch("app.group_decision.emotion.predict.Path.exists", return_value=True), \
         patch("app.group_decision.emotion.predict.Path.is_file", return_value=True), \
         patch("app.group_decision.emotion.predict.json.load", return_value=dummy_thresholds):

        # 1. Raw probabilities mode
        raw_results = predict(texts, apply_thresholds=False, device="cpu")
        assert len(raw_results) == 2
        assert isinstance(raw_results[0], dict)
        assert len(raw_results[0]) == 28

        # 2. Thresholded mode
        thresholded_results = predict(texts, apply_thresholds=True, device="cpu")
        assert len(thresholded_results) == 2
        for item in thresholded_results:
            assert "text" in item
            assert "probabilities" in item
            assert "predicted_labels" in item
            assert isinstance(item["predicted_labels"], list)
            assert "admiration" in item["predicted_labels"]


def test_predict_labels_convenience_function(dummy_thresholds: dict[str, Any]) -> None:
    """Test predict_labels() function."""
    texts = ["Just one text"]

    with patch("app.group_decision.emotion.predict.AutoTokenizer.from_pretrained", return_value=DummyTokenizer()), \
         patch("app.group_decision.emotion.predict.AutoModelForSequenceClassification.from_pretrained", return_value=DummyEmotionModel(28)), \
         patch("app.group_decision.emotion.predict.Path.exists", return_value=True), \
         patch("app.group_decision.emotion.predict.Path.is_file", return_value=True), \
         patch("app.group_decision.emotion.predict.json.load", return_value=dummy_thresholds):

        labels = predict_labels(texts, device="cpu")
        assert isinstance(labels, list)
        assert len(labels) == 1
        assert isinstance(labels[0], list)


def test_predict_empty_and_single_string_inputs(mock_predictor: EmotionPredictor) -> None:
    """Test handling of empty list, empty string, and single string inputs."""
    # Empty list
    assert mock_predictor.predict_probabilities([]) == []
    assert mock_predictor.predict_labels([]) == []

    # Single string via predict()
    with patch("app.group_decision.emotion.predict.AutoTokenizer.from_pretrained", return_value=DummyTokenizer()), \
         patch("app.group_decision.emotion.predict.AutoModelForSequenceClassification.from_pretrained", return_value=DummyEmotionModel(28)), \
         patch("app.group_decision.emotion.predict.Path.exists", return_value=True):
        res = predict("Single string input", apply_thresholds=False, device="cpu")
        assert len(res) == 1
        assert len(res[0]) == 28
