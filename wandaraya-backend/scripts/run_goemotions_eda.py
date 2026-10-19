"""Load, clean, and perform Exploratory Data Analysis on GoEmotions for WANDARAYA Component 3.

Processes GoEmotions (simplified) from Hugging Face into multi-label format,
removes duplicate and invalid rows using official train/val/test splits,
computes imbalance weights, and exports EDA figures to data/group_decision/reports/figures/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from datasets import load_dataset
from sklearn.feature_extraction.text import TfidfVectorizer

# Reproducibility
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Paths relative to wandaraya-backend root
DATA_DIR = Path("data/group_decision")
PROCESSED_DATA_DIR = DATA_DIR / "processed"
FIGURES_DIR = DATA_DIR / "reports" / "figures"

# Figure styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.titlesize": 16,
    "figure.dpi": 300,
})

DEFAULT_EMOTION_LABELS: list[str] = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral"
]


def load_and_preprocess_split(split_data, label_names: list[str], split_name: str) -> pd.DataFrame:
    """Preprocess a split into cleaned multi-label DataFrame."""
    print(f"\n[+] Processing {split_name} split...")
    raw_df = pd.DataFrame(split_data)
    initial_count = len(raw_df)
    print(f"    Initial count: {initial_count:,}")

    # 1. Clean invalid / whitespace texts
    raw_df = raw_df.dropna(subset=["text"])
    raw_df["text"] = raw_df["text"].astype(str).str.strip()
    raw_df = raw_df[raw_df["text"].str.len() > 0]
    valid_text_count = len(raw_df)
    if initial_count != valid_text_count:
        print(f"    Removed {initial_count - valid_text_count} invalid text rows.")

    # 2. Multi-label binary encoding
    num_labels = len(label_names)
    binary_matrix = np.zeros((len(raw_df), num_labels), dtype=np.int32)

    for idx, label_indices in enumerate(raw_df["labels"]):
        for lbl_idx in label_indices:
            if 0 <= lbl_idx < num_labels:
                binary_matrix[idx, lbl_idx] = 1

    label_df = pd.DataFrame(binary_matrix, columns=label_names, index=raw_df.index)
    processed_df = pd.concat([raw_df[["id", "text"]], label_df], axis=1)

    # 3. Deduplicate texts and merge multi-labels via bitwise OR
    duplicate_mask = processed_df.duplicated(subset=["text"], keep=False)
    dup_count = int(duplicate_mask.sum())
    if dup_count > 0:
        print(f"    Found {dup_count} duplicate text occurrences. Merging multi-labels...")
        aggregated = processed_df.groupby("text")[label_names].max().reset_index()
        id_series = processed_df.groupby("text")["id"].first().reset_index()
        processed_df = pd.merge(id_series, aggregated, on="text")
        print(f"    Deduplicated count: {len(processed_df):,} (removed {valid_text_count - len(processed_df)})")
    else:
        print("    No duplicates found.")

    return processed_df


def plot_class_distribution(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_names: list[str],
    output_dir: Path
) -> None:
    """Plot and save class distribution across splits."""
    print("[+] Plotting class distribution...")
    train_counts = train_df[label_names].sum().rename("Train")
    val_counts = val_df[label_names].sum().rename("Val")
    test_counts = test_df[label_names].sum().rename("Test")

    counts_df = pd.concat([train_counts, val_counts, test_counts], axis=1)
    counts_df = counts_df.sort_values(by="Train", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 14))
    counts_df.plot(
        kind="barh",
        stacked=False,
        ax=ax,
        color=["#2b5c8f", "#e28743", "#38b000"],
        width=0.8
    )

    ax.set_title("GoEmotions (Simplified): Class Distribution Across Splits", pad=15)
    ax.set_xlabel("Sample Count (Log Scale)", labelpad=10)
    ax.set_xscale("log")
    ax.set_ylabel("Emotion Category", labelpad=10)
    ax.legend(title="Split", frameon=True)
    plt.tight_layout()

    save_path = output_dir / "class_distribution.png"
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"    Saved: {save_path}")


def plot_label_counts_per_sample(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_names: list[str],
    output_dir: Path
) -> None:
    """Plot distribution of number of labels per sample."""
    print("[+] Plotting label counts per sample...")
    train_sums = train_df[label_names].sum(axis=1)
    val_sums = val_df[label_names].sum(axis=1)
    test_sums = test_df[label_names].sum(axis=1)

    max_labels = int(max(train_sums.max(), val_sums.max(), test_sums.max()))

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.histplot(
        data=pd.DataFrame({"Train": train_sums, "Validation": val_sums, "Test": test_sums}),
        discrete=True,
        multiple="dodge",
        shrink=0.8,
        palette=["#2b5c8f", "#e28743", "#38b000"],
        ax=ax
    )

    ax.set_title("Multi-Label Cardinality (Labels Per Message)", pad=15)
    ax.set_xlabel("Number of Emotion Labels", labelpad=10)
    ax.set_ylabel("Frequency", labelpad=10)
    ax.set_xticks(range(0, max_labels + 1))
    ax.legend(["Train", "Validation", "Test"], title="Split", frameon=True)
    plt.tight_layout()

    save_path = output_dir / "label_counts_per_sample.png"
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"    Saved: {save_path}")


def plot_text_length_distribution(
    train_df: pd.DataFrame,
    output_dir: Path
) -> tuple[int, int]:
    """Plot word and character length histograms."""
    print("[+] Plotting text length distribution...")
    word_lengths = train_df["text"].apply(lambda s: len(s.split()))
    char_lengths = train_df["text"].apply(len)

    p90_words = int(np.percentile(word_lengths, 90))
    p95_words = int(np.percentile(word_lengths, 95))
    p99_words = int(np.percentile(word_lengths, 99))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    sns.histplot(word_lengths, bins=40, kde=True, color="#1d3557", ax=ax1)
    ax1.axvline(p95_words, color="#e63946", linestyle="--", label=f"95th percentile ({p95_words} words)")
    ax1.axvline(p99_words, color="#f4a261", linestyle=":", label=f"99th percentile ({p99_words} words)")
    ax1.set_title("Message Word Count Distribution")
    ax1.set_xlabel("Word Count")
    ax1.set_ylabel("Messages")
    ax1.legend(frameon=True)

    p95_chars = int(np.percentile(char_lengths, 95))
    p99_chars = int(np.percentile(char_lengths, 99))
    sns.histplot(char_lengths, bins=40, kde=True, color="#457b9d", ax=ax2)
    ax2.axvline(p95_chars, color="#e63946", linestyle="--", label=f"95th percentile ({p95_chars} chars)")
    ax2.axvline(p99_chars, color="#f4a261", linestyle=":", label=f"99th percentile ({p99_chars} chars)")
    ax2.set_title("Message Character Length Distribution")
    ax2.set_xlabel("Character Length")
    ax2.set_ylabel("Messages")
    ax2.legend(frameon=True)

    plt.tight_layout()
    save_path = output_dir / "text_length_distribution.png"
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"    Saved: {save_path}")

    return p95_words, p99_words


def compute_and_plot_class_imbalance(
    train_df: pd.DataFrame,
    label_names: list[str],
    output_dir: Path
) -> dict[str, float]:
    """Compute and plot positive weights (pos_weight) for BCEWithLogitsLoss."""
    print("[+] Computing class imbalance weights...")
    total_samples = len(train_df)
    class_counts = train_df[label_names].sum()

    pos_weights: dict[str, float] = {}
    for emotion in label_names:
        pos = class_counts[emotion]
        neg = total_samples - pos
        weight = float(neg / pos) if pos > 0 else 1.0
        pos_weights[emotion] = round(weight, 2)

    weights_series = pd.Series(pos_weights).sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(12, 10))
    colors = sns.color_palette("rocket", len(weights_series))
    weights_series.plot(kind="barh", ax=ax, color=colors)

    ax.set_title("BCEWithLogitsLoss Positive Class Weights (pos_weight)", pad=15)
    ax.set_xlabel("Negative / Positive Sample Ratio", labelpad=10)
    ax.set_ylabel("Emotion Category", labelpad=10)

    for i, v in enumerate(weights_series):
        ax.text(v + 1, i, f" {v:.1f}x", va="center", fontsize=8, color="#333333")

    plt.tight_layout()
    save_path = output_dir / "class_imbalance_weights.png"
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"    Saved: {save_path}")

    return pos_weights


def extract_and_plot_top_words(
    train_df: pd.DataFrame,
    label_names: list[str],
    output_dir: Path,
    top_n: int = 6
) -> None:
    """Extract and plot top distinguishing terms per emotion using TF-IDF."""
    print("[+] Extracting top distinguishing words per emotion...")
    target_emotions = [
        "joy", "excitement", "admiration", "gratitude",
        "anger", "annoyance", "disappointment", "disapproval",
        "fear", "nervousness", "confusion", "neutral"
    ]

    fig, axes = plt.subplots(3, 4, figsize=(16, 12), sharey=False)
    axes = axes.flatten()

    for idx, emotion in enumerate(target_emotions):
        ax = axes[idx]
        subset = train_df[train_df[emotion] == 1]
        if len(subset) == 0:
            continue

        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=2000,
            token_pattern=r"(?u)\b[a-zA-Z]{3,}\b"
        )
        tfidf_matrix = vectorizer.fit_transform(subset["text"])
        feature_names = np.array(vectorizer.get_feature_names_out())
        mean_tfidf = np.asarray(tfidf_matrix.mean(axis=0)).flatten()

        top_indices = np.argsort(mean_tfidf)[::-1][:top_n]
        top_words = feature_names[top_indices]
        top_scores = mean_tfidf[top_indices]

        y_pos = np.arange(len(top_words))
        ax.barh(y_pos, top_scores, color="#0077b6", align="center")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(top_words)
        ax.invert_yaxis()
        ax.set_title(f"{emotion.upper()} (n={len(subset)})", fontsize=11, fontweight="bold")
        ax.set_xlabel("Mean TF-IDF", fontsize=9)

    plt.suptitle("Top Distinguishing Words for Key Emotion Categories", y=1.02, fontsize=15)
    plt.tight_layout()
    save_path = output_dir / "top_words_per_emotion.png"
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"    Saved: {save_path}")


def main() -> None:
    """Execute GoEmotions preparation and EDA pipeline."""
    print("=" * 70)
    print(" WANDARAYA - Component 3: GoEmotions Data Preparation & EDA")
    print("=" * 70)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[*] Figures directory: {FIGURES_DIR.resolve()}")
    print(f"[*] Processed data directory: {PROCESSED_DATA_DIR.resolve()}")

    print("[*] Loading GoEmotions (simplified) from Hugging Face...")
    try:
        raw_dataset = load_dataset("go_emotions", "simplified")
    except Exception as e:
        print(f"[!] Primary load notice ({e}). Retrying with full hub id...")
        raw_dataset = load_dataset("google-research-datasets/go_emotions", "simplified")

    label_feature = raw_dataset["train"].features.get("labels")
    if label_feature and hasattr(label_feature, "feature") and hasattr(label_feature.feature, "names"):
        label_names = label_feature.feature.names
    else:
        label_names = DEFAULT_EMOTION_LABELS

    # Preprocess splits
    train_df = load_and_preprocess_split(raw_dataset["train"], label_names, "train")
    val_df = load_and_preprocess_split(raw_dataset["validation"], label_names, "validation")
    test_df = load_and_preprocess_split(raw_dataset["test"], label_names, "test")

    # Generate EDA figures
    print("\n" + "=" * 70)
    print(" Generating Diagnostic EDA Figures")
    print("=" * 70)
    plot_class_distribution(train_df, val_df, test_df, label_names, FIGURES_DIR)
    plot_label_counts_per_sample(train_df, val_df, test_df, label_names, FIGURES_DIR)
    p95_words, p99_words = plot_text_length_distribution(train_df, FIGURES_DIR)
    pos_weights = compute_and_plot_class_imbalance(train_df, label_names, FIGURES_DIR)
    extract_and_plot_top_words(train_df, label_names, FIGURES_DIR)

    # Summary
    total_train = len(train_df)
    most_frequent = train_df[label_names].sum().idxmax()
    least_frequent = train_df[label_names].sum().idxmin()
    max_count = train_df[most_frequent].sum()
    min_count = train_df[least_frequent].sum()
    imbalance_ratio = max_count / min_count if min_count > 0 else float("inf")

    print("\n" + "=" * 70)
    print(" Summary & Model Training Insights")
    print("=" * 70)
    print(f"  - Train Samples Cleaned            : {total_train:,}")
    print(f"  - Validation Samples Cleaned       : {len(val_df):,}")
    print(f"  - Test Samples Cleaned             : {len(test_df):,}")
    print(f"  - Top Class                        : '{most_frequent}' ({max_count:,} samples, {max_count/total_train*100:.1f}%)")
    print(f"  - Rarest Class                     : '{least_frequent}' ({min_count:,} samples, {min_count/total_train*100:.2f}%)")
    print(f"  - Class Imbalance Ratio            : {imbalance_ratio:.1f} : 1")
    print(f"  - 95th Percentile Word Length      : {p95_words} words")
    print(f"  - 99th Percentile Word Length      : {p99_words} words")
    print("=" * 70)
    print("[SUCCESS] GoEmotions EDA complete. All figures saved to data/group_decision/reports/figures/.")


if __name__ == "__main__":
    main()
