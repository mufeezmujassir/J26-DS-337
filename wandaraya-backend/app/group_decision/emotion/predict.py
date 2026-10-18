"""Inference and emotion prediction module using fine-tuned RoBERTa.

WANDARAYA Component 3: Emotional Intelligence & Group Decision Agent (Step 6 Stage 1).
Provides high-performance inference for 28 GoEmotions categories with options to:
- Return raw probabilities for all 28 emotions
- Apply saved global or per-class decision thresholds
- Run batch predictions with automatic hardware acceleration
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from typing import Any, Sequence

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.emotion_baseline import DEFAULT_GOEMOTIONS_LABELS

# Default production locations
DEFAULT_MODEL_DIR = Path("models/roberta_emotion")
DEFAULT_THRESHOLDS_PATH = DEFAULT_MODEL_DIR / "thresholds.json"



class EmotionPredictor:
    """Encapsulates loaded RoBERTa model, tokenizer, and thresholds for fast inference."""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        thresholds_path: str | Path | None = None,
        model: Any | None = None,
        tokenizer: Any | None = None,
        thresholds_data: dict[str, Any] | None = None,
        device: str | torch.device | None = None,
        max_length: int = 64,
    ) -> None:
        self.max_length = max_length

        # Set execution device
        if device is None:
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = torch.device("mps")
            else:
                self.device = torch.device("cpu")
        else:
            self.device = torch.device(device)

        # Allow injected mock/preloaded models (ideal for tests and embedded services)
        if model is not None and tokenizer is not None:
            self.model = model
            self.tokenizer = tokenizer
        else:
            model_path = Path(model_dir or DEFAULT_MODEL_DIR)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"RoBERTa emotion model not found at {model_path.resolve()}. "
                    "Run src/emotion/train_roberta.py first to fine-tune the model."
                )
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_path)

        self.model.to(self.device)
        self.model.eval()

        # Load thresholds
        self.thresholds_data = thresholds_data or self._load_thresholds(thresholds_path or DEFAULT_THRESHOLDS_PATH)
        self.label_names = self.thresholds_data.get("label_names", list(DEFAULT_GOEMOTIONS_LABELS))
        self.global_threshold = float(self.thresholds_data.get("global_threshold", 0.5))
        self.per_class_thresholds = self.thresholds_data.get(
            "per_class_thresholds",
            {name: self.global_threshold for name in self.label_names},
        )

    def _load_thresholds(self, path: str | Path) -> dict[str, Any]:
        p = Path(path)
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Fallback if thresholds file is missing
        return {
            "global_threshold": 0.5,
            "per_class_thresholds": {name: 0.5 for name in DEFAULT_GOEMOTIONS_LABELS},
            "label_names": list(DEFAULT_GOEMOTIONS_LABELS),
        }

    def predict_probabilities(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[dict[str, float]]:
        """Compute multi-label probabilities for all 28 emotions."""
        if not texts:
            return []

        all_probs: list[dict[str, float]] = []
        use_amp = (self.device.type == "cuda")

        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch_texts = [str(t) for t in texts[i : i + batch_size]]
                encoding = self.tokenizer(
                    batch_texts,
                    truncation=True,
                    padding=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                input_ids = encoding["input_ids"].to(self.device)
                attention_mask = encoding["attention_mask"].to(self.device)

                if use_amp:
                    with torch.amp.autocast("cuda"):
                        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                else:
                    outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)

                batch_probs = torch.sigmoid(outputs.logits).cpu().numpy()

                for row in batch_probs:
                    prob_dict = {
                        self.label_names[idx]: round(float(row[idx]), 4)
                        for idx in range(len(self.label_names))
                    }
                    all_probs.append(prob_dict)

        return all_probs

    def predict_labels(
        self,
        texts: list[str],
        threshold_strategy: str = "per_class",
        batch_size: int = 32,
    ) -> list[list[str]]:
        """Predict active emotion labels applying the chosen threshold strategy."""
        probs_list = self.predict_probabilities(texts, batch_size=batch_size)
        predictions: list[list[str]] = []

        for p_dict in probs_list:
            active_labels = []
            for name, score in p_dict.items():
                if threshold_strategy == "global":
                    t = self.global_threshold
                else:
                    t = float(self.per_class_thresholds.get(name, self.global_threshold))

                if score >= t:
                    active_labels.append(name)

            # If no emotion passes the threshold, default to neutral if score > 0.2
            if not active_labels and "neutral" in p_dict and p_dict["neutral"] >= 0.2:
                active_labels.append("neutral")

            predictions.append(active_labels)

        return predictions


# Module-level predictor cache for efficient repeated predict() calls
_GLOBAL_PREDICTOR: EmotionPredictor | None = None


def get_default_predictor(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    thresholds_path: str | Path | None = None,
    device: str | torch.device | None = None,
) -> EmotionPredictor:
    """Retrieve or create cached global EmotionPredictor instance."""
    global _GLOBAL_PREDICTOR
    if _GLOBAL_PREDICTOR is None:
        _GLOBAL_PREDICTOR = EmotionPredictor(
            model_dir=model_dir,
            thresholds_path=thresholds_path,
            device=device,
        )
    return _GLOBAL_PREDICTOR


def predict(
    texts: list[str] | str,
    apply_thresholds: bool = False,
    threshold_strategy: str = "per_class",
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    thresholds_path: str | Path | None = None,
    device: str | torch.device | None = None,
    batch_size: int = 32,
    max_length: int = 64,
) -> list[dict[str, float]] | list[dict[str, Any]]:
    """Predict emotions for input texts using fine-tuned RoBERTa.

    Args:
        texts: A string or list of text messages.
        apply_thresholds: If False, returns list of dicts with all 28 emotion probabilities.
                          If True, also includes 'predicted_labels' according to thresholds.
        threshold_strategy: 'per_class' (default) or 'global'.
        model_dir: Directory containing fine-tuned model and tokenizer.
        thresholds_path: Path to thresholds.json file.
        device: Device to run inference on ('cpu', 'cuda', etc.).
        batch_size: Batch size for tokenization and model inference.
        max_length: Max sequence length for tokenizer.

    Returns:
        When apply_thresholds=False:
            list[dict[str, float]]: List of mappings from all 28 emotion names to probabilities.
        When apply_thresholds=True:
            list[dict[str, Any]]: List containing 'text', 'probabilities', and 'predicted_labels'.
    """
    if isinstance(texts, str):
        text_list = [texts]
    else:
        text_list = list(texts)

    if not text_list:
        return []

    predictor = EmotionPredictor(
        model_dir=model_dir,
        thresholds_path=thresholds_path,
        device=device,
        max_length=max_length,
    )

    probs = predictor.predict_probabilities(text_list, batch_size=batch_size)

    if not apply_thresholds:
        return probs

    labels = predictor.predict_labels(text_list, threshold_strategy=threshold_strategy, batch_size=batch_size)
    combined: list[dict[str, Any]] = []
    for text, prob_map, pred_lbls in zip(text_list, probs, labels):
        combined.append({
            "text": text,
            "probabilities": prob_map,
            "predicted_labels": pred_lbls,
        })

    return combined


def predict_labels(
    texts: list[str] | str,
    threshold_strategy: str = "per_class",
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    thresholds_path: str | Path | None = None,
    device: str | torch.device | None = None,
) -> list[list[str]]:
    """Convenience helper returning directly the list of predicted emotion labels per text."""
    if isinstance(texts, str):
        text_list = [texts]
    else:
        text_list = list(texts)

    if not text_list:
        return []

    predictor = EmotionPredictor(
        model_dir=model_dir,
        thresholds_path=thresholds_path,
        device=device,
    )
    return predictor.predict_labels(text_list, threshold_strategy=threshold_strategy)
