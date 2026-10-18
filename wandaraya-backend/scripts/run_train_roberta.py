"""Fine-tuning RoBERTa for multi-label emotion classification on GoEmotions.

WANDARAYA Component 3: Emotional Intelligence & Group Decision Agent (Step 6 Stage 1).
Fine-tunes roberta-base on 28 GoEmotions simplified categories using BCEWithLogitsLoss
with frequency-based positive class weighting, linear warmup, fp16 precision,
early stopping on validation Macro-F1, and validation threshold tuning.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import f1_score
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from emotion_baseline import (
    DEFAULT_GOEMOTIONS_LABELS,
    load_config,
    load_goemotions_splits,
    set_seed,
)


class GoEmotionsDataset(Dataset):
    """PyTorch Dataset for tokenized GoEmotions texts and multi-label targets."""

    def __init__(
        self,
        texts: list[str],
        labels: np.ndarray,
        tokenizer: Any,
        max_length: int = 64,
    ) -> None:
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        text = str(self.texts[idx])
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        item = {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.float32),
        }
        return item


def compute_pos_weights(y_train: np.ndarray, max_clip: float = 10.0) -> torch.Tensor:
    """Compute pos_weight for BCEWithLogitsLoss from train split label frequencies.

    pos_weight = (total_samples - pos_count) / pos_count, clipped to max_clip.
    """
    total_samples = len(y_train)
    pos_counts = y_train.sum(axis=0)
    pos_weights = np.zeros(y_train.shape[1], dtype=np.float32)

    for i in range(y_train.shape[1]):
        pos = pos_counts[i]
        if pos > 0:
            weight = (total_samples - pos) / pos
            pos_weights[i] = min(float(weight), float(max_clip))
        else:
            pos_weights[i] = 1.0

    print(f"[*] Computed BCE pos_weights (min={pos_weights.min():.2f}, max={pos_weights.max():.2f}, clip={max_clip})")
    return torch.tensor(pos_weights, dtype=torch.float32)


def get_device() -> torch.device:
    """Determine best available hardware accelerator."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def tune_validation_thresholds(
    val_probs: np.ndarray,
    val_targets: np.ndarray,
    label_names: list[str],
    min_t: float = 0.1,
    max_t: float = 0.9,
    step: float = 0.02,
) -> tuple[float, float, dict[str, float], float]:
    """Tune both global threshold and per-class thresholds on validation split."""
    thresholds_grid = np.arange(min_t, max_t + (step / 2.0), step)

    # 1. Global threshold tuning (single threshold optimizing Macro-F1 across all classes)
    print(f"[*] Tuning single global threshold (grid {min_t} to {max_t}, step {step})...")
    best_global_t = 0.5
    best_global_macro_f1 = -1.0

    for t in thresholds_grid:
        t_val = round(float(t), 4)
        pred = (val_probs >= t_val).astype(int)
        score = float(f1_score(val_targets, pred, average="macro", zero_division=0))
        if score > best_global_macro_f1:
            best_global_macro_f1 = score
            best_global_t = t_val

    print(f"    Optimal Global Threshold: {best_global_t:.4f} (Validation Macro-F1: {best_global_macro_f1:.4f})")

    # 2. Per-class threshold tuning (each class selects threshold maximizing its own F1)
    print(f"[*] Tuning per-class thresholds for {len(label_names)} emotion classes...")
    per_class_thresholds: dict[str, float] = {}

    for c_idx, class_name in enumerate(label_names):
        y_true_c = val_targets[:, c_idx]
        y_prob_c = val_probs[:, c_idx]

        best_c_t = 0.5
        best_c_f1 = -1.0

        for t in thresholds_grid:
            t_val = round(float(t), 4)
            pred_c = (y_prob_c >= t_val).astype(int)
            f1_c = float(f1_score(y_true_c, pred_c, average="binary", zero_division=0))
            if f1_c > best_c_f1:
                best_c_f1 = f1_c
                best_c_t = t_val

        per_class_thresholds[class_name] = best_c_t

    # Evaluate Macro-F1 when applying individual per-class thresholds
    per_class_vector = np.array([per_class_thresholds[c] for c in label_names])
    pred_per_class = (val_probs >= per_class_vector).astype(int)
    val_macro_f1_per_class = float(f1_score(val_targets, pred_per_class, average="macro", zero_division=0))
    print(f"    Validation Macro-F1 with Per-Class Thresholds: {val_macro_f1_per_class:.4f}")

    return best_global_t, best_global_macro_f1, per_class_thresholds, val_macro_f1_per_class


def plot_training_history(
    train_losses: list[float],
    val_losses: list[float],
    val_macro_f1s: list[float],
    output_path: str | Path,
) -> None:
    """Plot and save training and validation loss along with validation Macro-F1."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    epochs = range(1, len(train_losses) + 1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)

    # Loss curve
    ax1.plot(epochs, train_losses, "o-", color="#1f77b4", label="Train BCE Loss", linewidth=2)
    ax1.plot(epochs, val_losses, "s--", color="#ff7f0e", label="Validation BCE Loss", linewidth=2)
    ax1.set_title("Training & Validation Loss", fontsize=13, pad=10)
    ax1.set_xlabel("Epoch", fontsize=11)
    ax1.set_ylabel("Loss", fontsize=11)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(frameon=True)

    # Macro-F1 curve
    ax2.plot(epochs, val_macro_f1s, "d-", color="#2ca02c", label="Validation Macro-F1", linewidth=2)
    ax2.set_title("Validation Macro-F1 (Early Stopping Metric)", fontsize=13, pad=10)
    ax2.set_xlabel("Epoch", fontsize=11)
    ax2.set_ylabel("Macro-F1 Score", fontsize=11)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(frameon=True)

    plt.suptitle("RoBERTa-base GoEmotions Multi-Label Fine-Tuning Curves", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"[*] Training curves plot saved to: {out.resolve()}")


def train_roberta_model(
    config_path: str | Path = "configs/config.yaml",
    checkpoint_dir_override: str | Path | None = None,
) -> dict[str, Any]:
    """Fine-tune roberta-base on GoEmotions dataset according to Step 6 specs."""
    config = load_config(config_path)
    seed = int(config.get("seed", 42))
    set_seed(seed)

    roberta_cfg = config.get("roberta_emotion", {})
    model_name = roberta_cfg.get("model_name_or_path", "roberta-base")
    dataset_cfg = roberta_cfg.get("dataset", {})
    train_cfg = roberta_cfg.get("training", {})
    tuning_cfg = roberta_cfg.get("threshold_tuning", {})
    paths_cfg = roberta_cfg.get("paths", {})

    lr = float(train_cfg.get("learning_rate", 2e-5))
    weight_decay = float(train_cfg.get("weight_decay", 0.01))
    batch_size = int(train_cfg.get("batch_size", 32))
    max_length = int(train_cfg.get("max_length", 64))
    warmup_ratio = float(train_cfg.get("warmup_ratio", 0.1))
    max_epochs = int(train_cfg.get("max_epochs", 5))
    fp16_enabled = bool(train_cfg.get("fp16", True))
    patience = int(train_cfg.get("early_stopping_patience", 2))
    pos_weight_clip = float(train_cfg.get("pos_weight_max_clip", 10.0))

    model_dir = Path(paths_cfg.get("model_dir", "models/roberta_emotion"))
    checkpoint_dir = Path(checkpoint_dir_override or paths_cfg.get("checkpoint_dir", model_dir / "checkpoints"))
    thresholds_path = Path(paths_cfg.get("thresholds_json", model_dir / "thresholds.json"))
    figures_dir = Path(paths_cfg.get("figures_dir", "reports/figures"))

    model_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    device = get_device()
    use_amp = (device.type == "cuda" and fp16_enabled)
    print(f"[*] Training Device: {device} (AMP fp16: {use_amp})")

    # 1. Load GoEmotions Splits (exact same official splits as baseline)
    texts_by_split, labels_by_split, label_names = load_goemotions_splits(
        hf_path=dataset_cfg.get("hf_path", "google-research-datasets/go_emotions"),
        hf_fallback_path=dataset_cfg.get("hf_fallback_path", "go_emotions"),
        config_name=dataset_cfg.get("config_name", "simplified"),
        num_classes=int(dataset_cfg.get("num_classes", 28)),
    )

    num_classes = len(label_names)
    print(f"[*] Initializing Tokenizer: '{model_name}' (max_length={max_length})...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    train_dataset = GoEmotionsDataset(texts_by_split["train"], labels_by_split["train"], tokenizer, max_length)
    val_dataset = GoEmotionsDataset(texts_by_split["validation"], labels_by_split["validation"], tokenizer, max_length)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, pin_memory=(device.type == "cuda"))
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, pin_memory=(device.type == "cuda"))

    # 2. Compute pos_weight from train labels
    pos_weights = compute_pos_weights(labels_by_split["train"], max_clip=pos_weight_clip).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weights)

    # 3. Model setup
    print(f"[*] Loading pretrained {model_name} for multi-label classification (outputs={num_classes})...")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_classes,
        problem_type="multi_label_classification",
    )
    model.to(device)

    # Optimizer with decoupled weight decay (exclude bias and LayerNorm)
    no_decay = ["bias", "LayerNorm.weight", "layer_norm.weight"]
    optimizer_grouped_parameters = [
        {
            "params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
            "weight_decay": weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(optimizer_grouped_parameters, lr=lr)

    total_training_steps = len(train_loader) * max_epochs
    warmup_steps = int(total_training_steps * warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_training_steps,
    )

    # Mixed precision scaler (compatible with modern torch)
    if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    else:
        scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    # 4. Training loop with early stopping
    print(f"\n" + "=" * 76)
    print(f" Starting Fine-Tuning: max_epochs={max_epochs}, patience={patience}, lr={lr}")
    print("=" * 76)

    best_val_macro_f1 = -1.0
    patience_counter = 0
    train_loss_history: list[float] = []
    val_loss_history: list[float] = []
    val_f1_history: list[float] = []

    best_checkpoint_path = checkpoint_dir / "best_model"
    best_checkpoint_path.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, max_epochs + 1):
        model.train()
        total_train_loss = 0.0

        for batch_idx, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            targets = batch["labels"].to(device)

            optimizer.zero_grad()

            if use_amp:
                with torch.amp.autocast("cuda"):
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    loss = criterion(outputs.logits, targets)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(outputs.logits, targets)
                loss.backward()
                optimizer.step()

            scheduler.step()
            total_train_loss += loss.item()

            if (batch_idx + 1) % 100 == 0 or (batch_idx + 1) == len(train_loader):
                print(f"  Epoch {epoch}/{max_epochs} | Step {batch_idx + 1}/{len(train_loader)} | Batch Loss: {loss.item():.4f}")

        avg_train_loss = total_train_loss / len(train_loader)
        train_loss_history.append(avg_train_loss)

        # Validation evaluation
        model.eval()
        total_val_loss = 0.0
        val_probs_list: list[np.ndarray] = []

        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                targets = batch["labels"].to(device)

                if use_amp:
                    with torch.amp.autocast("cuda"):
                        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                        loss = criterion(outputs.logits, targets)
                else:
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    loss = criterion(outputs.logits, targets)

                total_val_loss += loss.item()
                probs = torch.sigmoid(outputs.logits).cpu().numpy()
                val_probs_list.append(probs)

        avg_val_loss = total_val_loss / len(val_loader)
        val_loss_history.append(avg_val_loss)

        epoch_val_probs = np.vstack(val_probs_list)
        # Default 0.5 threshold macro-F1 for tracking early stopping
        val_preds_default = (epoch_val_probs >= 0.5).astype(int)
        val_macro_f1 = float(f1_score(labels_by_split["validation"], val_preds_default, average="macro", zero_division=0))
        val_f1_history.append(val_macro_f1)

        print(f"\n--- Epoch {epoch}/{max_epochs} Results ---")
        print(f"  Train BCE Loss: {avg_train_loss:.4f} | Val BCE Loss: {avg_val_loss:.4f} | Val Macro-F1 (t=0.5): {val_macro_f1:.4f}")

        # Early stopping check
        if val_macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = val_macro_f1
            patience_counter = 0
            print(f"  [+] New best validation Macro-F1: {best_val_macro_f1:.4f}. Saving checkpoint to: {best_checkpoint_path.resolve()}")
            model.save_pretrained(best_checkpoint_path)
            tokenizer.save_pretrained(best_checkpoint_path)
        else:
            patience_counter += 1
            print(f"  [!] No improvement in Macro-F1 ({val_macro_f1:.4f} <= {best_val_macro_f1:.4f}). Early stopping counter: {patience_counter}/{patience}")
            if patience_counter >= patience:
                print(f"[!] Early stopping triggered at epoch {epoch} (patience={patience} reached).")
                break

    # Save training curves plot
    curves_plot_path = figures_dir / "roberta_training_curves.png"
    plot_training_history(train_loss_history, val_loss_history, val_f1_history, curves_plot_path)

    # 5. Reload best model for threshold tuning and final artifact saving
    print(f"\n[*] Reloading best checkpoint from {best_checkpoint_path.resolve()}...")
    best_model = AutoModelForSequenceClassification.from_pretrained(best_checkpoint_path).to(device)
    best_model.eval()

    # Collect validation predictions from the best model
    val_probs_list.clear()
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            if use_amp:
                with torch.amp.autocast("cuda"):
                    outputs = best_model(input_ids=input_ids, attention_mask=attention_mask)
            else:
                outputs = best_model(input_ids=input_ids, attention_mask=attention_mask)
            val_probs_list.append(torch.sigmoid(outputs.logits).cpu().numpy())

    final_val_probs = np.vstack(val_probs_list)
    val_targets = labels_by_split["validation"]

    # 6. Validation Threshold Tuning
    min_t = float(tuning_cfg.get("min_threshold", 0.1))
    max_t = float(tuning_cfg.get("max_threshold", 0.9))
    step_t = float(tuning_cfg.get("step", 0.02))

    global_t, global_val_f1, per_class_t, per_class_val_f1 = tune_validation_thresholds(
        val_probs=final_val_probs,
        val_targets=val_targets,
        label_names=label_names,
        min_t=min_t,
        max_t=max_t,
        step=step_t,
    )

    # 7. Save model, tokenizer, and thresholds.json
    print(f"[*] Exporting final production model and tokenizer to: {model_dir.resolve()}")
    best_model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)

    thresholds_payload = {
        "global_threshold": global_t,
        "validation_macro_f1_global": round(global_val_f1, 4),
        "per_class_thresholds": per_class_t,
        "validation_macro_f1_per_class": round(per_class_val_f1, 4),
        "label_names": label_names,
        "tuning_grid": {
            "min_threshold": min_t,
            "max_threshold": max_t,
            "step": step_t,
        },
    }
    with open(thresholds_path, "w", encoding="utf-8") as f:
        json.dump(thresholds_payload, f, indent=2)
    print(f"[*] Tuned thresholds saved to: {thresholds_path.resolve()}")

    return {
        "model_dir": str(model_dir),
        "thresholds_path": str(thresholds_path),
        "best_val_macro_f1": best_val_macro_f1,
        "global_threshold": global_t,
        "per_class_thresholds": per_class_t,
        "curves_plot_path": str(curves_plot_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune RoBERTa-base on GoEmotions (Step 6 Stage 1)")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yaml",
        help="Path to YAML configuration file (default: configs/config.yaml)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default=None,
        help="Optional checkpoint directory (e.g. Google Drive path)",
    )
    parser.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Skip automatic test evaluation after training completes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 76)
    print("  WANDARAYA C3 - STEP 6: ROBERTA EMOTION MODEL TRAINING (STAGE 1)")
    print("=" * 76)

    train_results = train_roberta_model(
        config_path=args.config,
        checkpoint_dir_override=args.checkpoint_dir,
    )
    print("\n[+] RoBERTa Training & Threshold Tuning Finished Successfully!")

    if not args.no_evaluate:
        print("\n[*] Invoking evaluation and error analysis module...")
        from run_emotion_evaluation import run_evaluation
        run_evaluation(config_path=args.config)


if __name__ == "__main__":
    main()
