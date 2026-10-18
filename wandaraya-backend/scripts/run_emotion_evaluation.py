"""Comprehensive evaluation and error analysis for RoBERTa emotion model.

WANDARAYA Component 3: Emotional Intelligence & Group Decision Agent (Step 6 Stage 1).
Evaluates fine-tuned RoBERTa on GoEmotions test split with:
- Global threshold vs. Per-class threshold strategies
- Identical metrics functions as src/emotion/baseline.py
- Comparison benchmark table against TF-IDF baseline results
- Error analysis: top 15 confused label pairs & 5 worst-performing classes with examples
- Export of metrics to reports/roberta_emotion_results.json and diagnostic figures
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Ensure root directory is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from emotion_baseline import (
    DEFAULT_GOEMOTIONS_LABELS,
    evaluate_model,
    load_config,
    load_goemotions_splits,
)


class TextDataset(Dataset):
    """Simple PyTorch Dataset for batch tokenization."""

    def __init__(self, texts: list[str], tokenizer: Any, max_length: int = 64) -> None:
        self.texts = texts
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        encoding = self.tokenizer(
            str(self.texts[idx]),
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
        }


def get_inference_device() -> torch.device:
    """Select best available device for evaluation inference."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def compute_test_probabilities(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    batch_size: int = 32,
    max_length: int = 64,
    device: torch.device | None = None,
) -> np.ndarray:
    """Run batch inference over test texts and return sigmoid probabilities."""
    if device is None:
        device = get_inference_device()

    model.eval()
    model.to(device)

    dataset = TextDataset(texts, tokenizer, max_length=max_length)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

    probs_list: list[np.ndarray] = []
    use_amp = (device.type == "cuda")

    print(f"[*] Running test inference ({len(texts):,} texts, batch_size={batch_size}, device={device})...")
    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            if use_amp:
                with torch.amp.autocast("cuda"):
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            else:
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)

            probs = torch.sigmoid(outputs.logits).cpu().numpy()
            probs_list.append(probs)

    return np.vstack(probs_list)


def analyze_confused_label_pairs(
    texts: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    label_names: list[str],
    top_k: int = 15,
) -> list[dict[str, Any]]:
    """Identify the top K most frequently confused label pairs.

    Pairs where true label was present but predicted absent (FN), and another
    label was predicted present but true was absent (FP) in the same text.
    """
    pair_counter: Counter[tuple[str, str]] = Counter()

    for i in range(len(texts)):
        true_indices = set(np.where(y_true[i] == 1)[0])
        pred_indices = set(np.where(y_pred[i] == 1)[0])

        missed = true_indices - pred_indices       # FN
        false_alarms = pred_indices - true_indices # FP

        for m_idx in missed:
            for f_idx in false_alarms:
                pair = (label_names[m_idx], label_names[f_idx])
                pair_counter[pair] += 1

    top_pairs = pair_counter.most_common(top_k)
    results = []
    for rank, ((true_lbl, pred_lbl), count) in enumerate(top_pairs, 1):
        results.append({
            "rank": rank,
            "true_label": true_lbl,
            "predicted_label": pred_lbl,
            "count": int(count),
        })

    return results


def analyze_worst_classes_with_examples(
    texts: list[str],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    per_class_metrics: dict[str, dict[str, Any]],
    label_names: list[str],
    bottom_k: int = 5,
    samples_per_type: int = 2,
) -> list[dict[str, Any]]:
    """Extract bottom K worst-performing classes by F1 and sample misclassified texts."""
    sorted_classes = sorted(per_class_metrics.items(), key=lambda x: x[1]["f1"])
    worst_classes = sorted_classes[:bottom_k]

    worst_analysis: list[dict[str, Any]] = []

    for class_name, metrics in worst_classes:
        c_idx = label_names.index(class_name)
        true_c = y_true[:, c_idx]
        pred_c = y_pred[:, c_idx]

        fn_indices = np.where((true_c == 1) & (pred_c == 0))[0]
        fp_indices = np.where((true_c == 0) & (pred_c == 1))[0]

        fn_examples = []
        for idx in fn_indices[:samples_per_type]:
            actual_labels = [label_names[j] for j in np.where(y_true[idx] == 1)[0]]
            predicted_labels = [label_names[j] for j in np.where(y_pred[idx] == 1)[0]]
            fn_examples.append({
                "text": str(texts[idx]),
                "true_labels": actual_labels,
                "predicted_labels": predicted_labels,
            })

        fp_examples = []
        for idx in fp_indices[:samples_per_type]:
            actual_labels = [label_names[j] for j in np.where(y_true[idx] == 1)[0]]
            predicted_labels = [label_names[j] for j in np.where(y_pred[idx] == 1)[0]]
            fp_examples.append({
                "text": str(texts[idx]),
                "true_labels": actual_labels,
                "predicted_labels": predicted_labels,
            })

        worst_analysis.append({
            "class_name": class_name,
            "f1_score": metrics["f1"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "support": metrics["support"],
            "false_negative_examples": fn_examples,
            "false_positive_examples": fp_examples,
        })

    return worst_analysis


def print_comparison_tables(
    baseline_data: dict[str, Any] | None,
    roberta_global_metrics: dict[str, Any],
    roberta_per_class_metrics: dict[str, Any],
    global_t: float,
) -> None:
    """Print ASCII comparison table between TF-IDF baseline and RoBERTa models."""
    base_m = baseline_data.get("test_metrics", {}) if baseline_data else {}

    print("\n" + "=" * 90)
    print("  WANDARAYA C3 - MODEL BENCHMARK COMPARISON (GOEMOTIONS TEST SET)")
    print("=" * 90)
    print(f"  {'Metric':<25} | {'TF-IDF Baseline':<16} | {'RoBERTa (Global)':<18} | {'RoBERTa (Per-Class)':<18} | {'Gain vs Base':<10}")
    print("-" * 90)

    rows = [
        ("Macro-F1", base_m.get("macro_f1", 0.0), roberta_global_metrics["macro_f1"], roberta_per_class_metrics["macro_f1"]),
        ("Micro-F1", base_m.get("micro_f1", 0.0), roberta_global_metrics["micro_f1"], roberta_per_class_metrics["micro_f1"]),
        ("Weighted-F1", base_m.get("weighted_f1", 0.0), roberta_global_metrics["weighted_f1"], roberta_per_class_metrics["weighted_f1"]),
        ("Subset Accuracy (Exact)", base_m.get("subset_accuracy", 0.0), roberta_global_metrics["subset_accuracy"], roberta_per_class_metrics["subset_accuracy"]),
        ("Macro Precision", base_m.get("macro_precision", 0.0), roberta_global_metrics["macro_precision"], roberta_per_class_metrics["macro_precision"]),
        ("Macro Recall", base_m.get("macro_recall", 0.0), roberta_global_metrics["macro_recall"], roberta_per_class_metrics["macro_recall"]),
    ]

    for name, b_val, g_val, p_val in rows:
        gain = p_val - b_val if b_val > 0 else 0.0
        gain_str = f"+{gain:.4f}" if gain >= 0 else f"{gain:.4f}"
        print(f"  {name:<25} | {b_val:<16.4f} | {g_val:<18.4f} | {p_val:<18.4f} | {gain_str:<10}")

    print("=" * 90)
    print(f"  * Tuned Global Threshold: {global_t:.4f} | Per-Class: 28 individual thresholds applied")
    print("-" * 90)


def print_error_analysis_report(
    confused_pairs: list[dict[str, Any]],
    worst_classes: list[dict[str, Any]],
) -> None:
    """Print error analysis tables to stdout."""
    print("\n" + "=" * 90)
    print("  ERROR ANALYSIS: TOP 15 MOST FREQUENTLY CONFUSED LABEL PAIRS")
    print("=" * 90)
    print(f"  {'Rank':<5} | {'True Label (Missed)':<25} | {'Predicted Label (False Alarm)':<30} | {'Occurrences':<12}")
    print("-" * 90)
    for p in confused_pairs:
        print(f"  {p['rank']:<5} | {p['true_label']:<25} | {p['predicted_label']:<30} | {p['count']:<12}")
    print("=" * 90)

    print("\n" + "=" * 90)
    print("  ERROR ANALYSIS: 5 WORST-PERFORMING CLASSES & DIAGNOSTIC SAMPLES")
    print("=" * 90)
    for c in worst_classes:
        print(f"\n[!] Class: {c['class_name'].upper()} (F1: {c['f1_score']:.4f}, Precision: {c['precision']:.4f}, Recall: {c['recall']:.4f}, Support: {c['support']})")

        print("    False Negative Sample (Model missed this true emotion):")
        if c["false_negative_examples"]:
            fn = c["false_negative_examples"][0]
            print(f"      - Text      : \"{fn['text']}\"")
            print(f"      - True      : {fn['true_labels']}")
            print(f"      - Predicted : {fn['predicted_labels']}")
        else:
            print("      - (No false negative examples found)")

        print("    False Positive Sample (Model falsely triggered this emotion):")
        if c["false_positive_examples"]:
            fp = c["false_positive_examples"][0]
            print(f"      - Text      : \"{fp['text']}\"")
            print(f"      - True      : {fp['true_labels']}")
            print(f"      - Predicted : {fp['predicted_labels']}")
        else:
            print("      - (No false positive examples found)")
    print("=" * 90 + "\n")


def plot_comparison_and_error_charts(
    baseline_data: dict[str, Any] | None,
    roberta_metrics: dict[str, Any],
    confused_pairs: list[dict[str, Any]],
    figures_dir: Path,
) -> None:
    """Plot and save comparison F1 chart and top confused pairs chart."""
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Per-class F1 Comparison Plot
    base_per_class = baseline_data.get("test_metrics", {}).get("per_class", {}) if baseline_data else {}
    rob_per_class = roberta_metrics.get("per_class", {})

    classes = sorted(rob_per_class.keys())
    rob_scores = [rob_per_class[c]["f1"] for c in classes]
    base_scores = [base_per_class.get(c, {}).get("f1", 0.0) for c in classes]

    y = np.arange(len(classes))
    height = 0.4

    fig, ax = plt.subplots(figsize=(12, 14), dpi=300)
    ax.barh(y - height / 2, base_scores, height, label="TF-IDF Baseline", color="#8ecae6", edgecolor="#219ebc")
    ax.barh(y + height / 2, rob_scores, height, label="RoBERTa (Per-Class Thresholds)", color="#023047", edgecolor="#fb8500")

    ax.set_ylabel("Emotion Category", fontsize=11)
    ax.set_xlabel("F1 Score", fontsize=11)
    ax.set_title("Per-Class F1 Benchmark: TF-IDF Baseline vs. RoBERTa-base (GoEmotions Test Split)", fontsize=13, pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(classes, fontsize=9)
    ax.set_xlim(0.0, 1.0)
    ax.grid(axis="x", linestyle=":", alpha=0.6)
    ax.legend(frameon=True, loc="lower right")
    plt.tight_layout()

    comp_chart_path = figures_dir / "roberta_vs_baseline_per_class_f1.png"
    plt.savefig(comp_chart_path, dpi=300)
    plt.close()
    print(f"[*] Comparison chart saved to: {comp_chart_path.resolve()}")

    # 2. Confused Label Pairs Chart
    if confused_pairs:
        pair_labels = [f"{p['true_label']} -> {p['predicted_label']}" for p in reversed(confused_pairs)]
        counts = [p["count"] for p in reversed(confused_pairs)]

        fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
        bars = ax.barh(pair_labels, counts, color="#d62828", edgecolor="#6a040f", height=0.65)
        for bar in bars:
            w = bar.get_width()
            ax.text(w + 0.5, bar.get_y() + bar.get_height() / 2, f"{int(w)}", va="center", fontsize=8)

        ax.set_xlabel("Frequency (Test Split Misclassifications)", fontsize=11)
        ax.set_title("Top 15 Most Frequently Confused Emotion Pairs (True -> Predicted)", fontsize=13, pad=15)
        ax.grid(axis="x", linestyle=":", alpha=0.6)
        plt.tight_layout()

        confusion_chart_path = figures_dir / "roberta_confused_label_pairs.png"
        plt.savefig(confusion_chart_path, dpi=300)
        plt.close()
        print(f"[*] Confused label pairs chart saved to: {confusion_chart_path.resolve()}")


def run_evaluation(config_path: str | Path = "configs/config.yaml") -> dict[str, Any]:
    """Execute complete Step 6 evaluation pipeline on GoEmotions test split."""
    config = load_config(config_path)
    roberta_cfg = config.get("roberta_emotion", {})
    paths_cfg = roberta_cfg.get("paths", {})
    dataset_cfg = roberta_cfg.get("dataset", {})

    model_dir = Path(paths_cfg.get("model_dir", "models/roberta_emotion"))
    thresholds_path = Path(paths_cfg.get("thresholds_json", model_dir / "thresholds.json"))
    results_path = Path(paths_cfg.get("results_json", "reports/roberta_emotion_results.json"))
    baseline_results_path = Path(paths_cfg.get("baseline_results_json", "reports/baseline_emotion_results.json"))
    figures_dir = Path(paths_cfg.get("figures_dir", "reports/figures"))

    if not model_dir.exists():
        raise FileNotFoundError(f"Trained RoBERTa model not found at: {model_dir.resolve()}. Run train_roberta.py first.")
    if not thresholds_path.is_file():
        raise FileNotFoundError(f"Tuned thresholds not found at: {thresholds_path.resolve()}.")

    # Load thresholds
    with open(thresholds_path, "r", encoding="utf-8") as f:
        thresholds_data = json.load(f)
    global_t = float(thresholds_data["global_threshold"])
    per_class_t_dict = thresholds_data["per_class_thresholds"]

    # Load baseline results if present
    baseline_data = None
    if baseline_results_path.is_file():
        with open(baseline_results_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)
        print(f"[*] Loaded baseline comparison benchmark from: {baseline_results_path.resolve()}")

    # Load test split
    texts_by_split, labels_by_split, label_names = load_goemotions_splits(
        hf_path=dataset_cfg.get("hf_path", "google-research-datasets/go_emotions"),
        hf_fallback_path=dataset_cfg.get("hf_fallback_path", "go_emotions"),
        config_name=dataset_cfg.get("config_name", "simplified"),
        num_classes=int(dataset_cfg.get("num_classes", 28)),
    )
    test_texts = texts_by_split["test"]
    y_test_true = labels_by_split["test"]

    # Load model and tokenizer
    print(f"[*] Loading fine-tuned model and tokenizer from: {model_dir.resolve()}...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)

    # Compute probabilities once on test set
    test_probs = compute_test_probabilities(
        model=model,
        tokenizer=tokenizer,
        texts=test_texts,
        batch_size=int(roberta_cfg.get("training", {}).get("batch_size", 32)),
        max_length=int(roberta_cfg.get("training", {}).get("max_length", 64)),
    )

    # Strategy (a): Single Global Threshold
    print(f"[*] Evaluating Strategy (a): Global threshold ({global_t:.4f})...")
    y_test_pred_global = (test_probs >= global_t).astype(int)
    global_metrics = evaluate_model(y_test_true, y_test_pred_global, label_names)

    # Strategy (b): Per-Class Thresholds
    print(f"[*] Evaluating Strategy (b): 28 Per-Class tuned thresholds...")
    per_class_vector = np.array([float(per_class_t_dict[name]) for name in label_names])
    y_test_pred_per_class = (test_probs >= per_class_vector).astype(int)
    per_class_strategy_metrics = evaluate_model(y_test_true, y_test_pred_per_class, label_names)

    # Error Analysis (using per-class predictions)
    print("[*] Performing error analysis...")
    confused_pairs = analyze_confused_label_pairs(
        texts=test_texts,
        y_true=y_test_true,
        y_pred=y_test_pred_per_class,
        label_names=label_names,
        top_k=15,
    )

    worst_classes_analysis = analyze_worst_classes_with_examples(
        texts=test_texts,
        y_true=y_test_true,
        y_pred=y_test_pred_per_class,
        per_class_metrics=per_class_strategy_metrics["per_class"],
        label_names=label_names,
        bottom_k=5,
    )

    # Print reports to stdout
    print_comparison_tables(baseline_data, global_metrics, per_class_strategy_metrics, global_t)
    print_error_analysis_report(confused_pairs, worst_classes_analysis)

    # Save Diagnostic Plots
    plot_comparison_and_error_charts(baseline_data, per_class_strategy_metrics, confused_pairs, figures_dir)

    # Save comprehensive results payload to JSON
    results_payload = {
        "model": "roberta-base",
        "dataset": "go_emotions (simplified)",
        "thresholds": {
            "global_threshold": global_t,
            "per_class_thresholds": per_class_t_dict,
        },
        "test_results_global_threshold": global_metrics,
        "test_results_per_class_thresholds": per_class_strategy_metrics,
        "error_analysis": {
            "top_15_confused_label_pairs": confused_pairs,
            "five_worst_performing_classes": worst_classes_analysis,
        },
        "baseline_comparison": {
            "baseline_macro_f1": baseline_data.get("test_metrics", {}).get("macro_f1") if baseline_data else None,
            "roberta_global_macro_f1": global_metrics["macro_f1"],
            "roberta_per_class_macro_f1": per_class_strategy_metrics["macro_f1"],
            "macro_f1_gain": round(
                per_class_strategy_metrics["macro_f1"] - (baseline_data.get("test_metrics", {}).get("macro_f1", 0.0) if baseline_data else 0.0),
                4,
            ),
        },
    }

    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    print(f"[*] Complete evaluation results saved to: {results_path.resolve()}")

    return results_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RoBERTa Emotion Model on GoEmotions Test Split")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yaml",
        help="Path to YAML configuration file (default: configs/config.yaml)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 90)
    print("  WANDARAYA C3 - STEP 6: ROBERTA TEST EVALUATION & ERROR ANALYSIS")
    print("=" * 90)
    run_evaluation(config_path=args.config)
    print("[SUCCESS] Step 6 evaluation and error analysis complete.")


if __name__ == "__main__":
    main()
