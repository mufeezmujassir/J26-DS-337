"""Validation and evaluation suite for Emotion Expression Intensity Estimator.


Implements:
1. Stratified sampling of 100 test messages across positive, negative, ambiguous,
   and neutral emotion categories into a blind rating sheet (`data/processed/intensity_rating_sheet.csv`).
2. Analysis of human ratings (1-5 scale) vs. estimator scores using Spearman rank correlation,
   two-sided p-value, and 1,000-iteration bootstrap 95% confidence interval.
3. Ablation study: Model-only, Lexical-only, Punctuation-only, Model+Lexical, and Full estimator.
4. Export of results to `reports/intensity_validation.json` and scatter plot to `reports/figures/intensity_scatter.png`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
from typing import Any

from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from group_decision.intensity.estimator import (
    DEFAULT_GOEMOTIONS_LABELS,
    DEFAULT_VALENCE_MAP,
    estimate_intensity,
    load_intensity_config,
)

RANDOM_SEED = 42
DEFAULT_SHEET_PATH = Path("data/group_decision/processed/intensity_rating_sheet.csv")
DEFAULT_RESULTS_PATH = Path("data/group_decision/reports/intensity_validation.json")
DEFAULT_FIGURE_PATH = Path("data/group_decision/reports/figures/intensity_scatter.png")


def sample_stratified_evaluation_set(
    output_path: str | Path = DEFAULT_SHEET_PATH,
    n_samples: int = 100,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Sample stratified messages from GoEmotions TEST set for blind human rating.

    Ensures balanced coverage across positive, negative, ambiguous, and neutral emotions.
    The resulting CSV contains ONLY id, text, human_rating (empty) to preserve blinding.
    """
    random.seed(seed)
    np.random.seed(seed)

    print("[*] Loading GoEmotions test split from Hugging Face...")
    try:
        raw_dataset = load_dataset("google-research-datasets/go_emotions", "simplified")
    except Exception:
        raw_dataset = load_dataset("go_emotions", "simplified")

    test_split = raw_dataset["test"]
    texts = [str(t).strip() for t in test_split["text"]]
    labels_list = test_split["labels"]

    # Extract class names
    label_feature = test_split.features.get("labels")
    if label_feature and hasattr(label_feature, "feature") and hasattr(label_feature.feature, "names"):
        label_names = list(label_feature.feature.names)
    else:
        label_names = list(DEFAULT_GOEMOTIONS_LABELS)

    # Classify messages into coarse valence categories for stratified sampling
    pos_set = set(DEFAULT_VALENCE_MAP["positive"])
    neg_set = set(DEFAULT_VALENCE_MAP["negative"])
    amb_set = set(DEFAULT_VALENCE_MAP["ambiguous"])

    stratified_buckets: dict[str, list[dict[str, Any]]] = {
        "positive": [],
        "negative": [],
        "ambiguous": [],
        "neutral": [],
    }

    for idx, (txt, lbls) in enumerate(zip(texts, labels_list)):
        if len(txt) < 8:
            continue
        emotion_names = {label_names[l] for l in lbls if l < len(label_names)}

        # Determine primary stratum
        if "neutral" in emotion_names and len(emotion_names) == 1:
            stratified_buckets["neutral"].append({"id": idx, "text": txt})
        elif emotion_names.intersection(pos_set) and not emotion_names.intersection(neg_set):
            stratified_buckets["positive"].append({"id": idx, "text": txt})
        elif emotion_names.intersection(neg_set) and not emotion_names.intersection(pos_set):
            stratified_buckets["negative"].append({"id": idx, "text": txt})
        elif emotion_names.intersection(amb_set):
            stratified_buckets["ambiguous"].append({"id": idx, "text": txt})

    # Allocation: 30 positive, 30 negative, 20 ambiguous, 20 neutral = 100
    target_counts = {
        "positive": int(n_samples * 0.30),
        "negative": int(n_samples * 0.30),
        "ambiguous": int(n_samples * 0.20),
        "neutral": n_samples - int(n_samples * 0.30) - int(n_samples * 0.30) - int(n_samples * 0.20),
    }

    selected_rows: list[dict[str, Any]] = []
    for bucket_name, count in target_counts.items():
        candidates = stratified_buckets[bucket_name]
        chosen = random.sample(candidates, min(count, len(candidates)))
        selected_rows.extend(chosen)

    # Shuffle the combined list so strata are randomly interleaved for blind rating
    random.shuffle(selected_rows)

    df_sheet = pd.DataFrame({
        "id": [f"INT-{i+1:03d}" for i in range(len(selected_rows))],
        "original_test_idx": [r["id"] for r in selected_rows],
        "text": [r["text"] for r in selected_rows],
        "human_rating": ["" for _ in range(len(selected_rows))],
    })

    # Save blind CSV: omit original_test_idx from rating sheet to keep rating completely blind
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    blind_export = df_sheet[["id", "text", "human_rating"]]
    blind_export.to_csv(out_file, index=False)
    print(f"[+] Blind intensity rating sheet created with {len(df_sheet)} samples: {out_file.resolve()}")

    return df_sheet


def compute_bootstrap_spearman_ci(
    x: np.ndarray,
    y: np.ndarray,
    n_bootstraps: int = 1000,
    confidence_level: float = 0.95,
    seed: int = RANDOM_SEED,
) -> tuple[float, float, tuple[float, float]]:
    """Compute Spearman correlation, p-value, and bootstrap confidence interval."""
    rng = np.random.default_rng(seed)
    corr_stat, p_val = spearmanr(x, y)

    n = len(x)
    boot_corrs: list[float] = []

    for _ in range(n_bootstraps):
        boot_idx = rng.choice(n, size=n, replace=True)
        x_boot = x[boot_idx]
        y_boot = y[boot_idx]
        # Avoid zero variance in small boot resamples
        if np.std(x_boot) > 1e-8 and np.std(y_boot) > 1e-8:
            r_b, _ = spearmanr(x_boot, y_boot)
            if not np.isnan(r_b):
                boot_corrs.append(float(r_b))

    alpha = 1.0 - confidence_level
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - (alpha / 2.0)) * 100.0

    ci_lower = float(np.percentile(boot_corrs, lower_pct)) if boot_corrs else float(corr_stat)
    ci_upper = float(np.percentile(boot_corrs, upper_pct)) if boot_corrs else float(corr_stat)

    return float(corr_stat), float(p_val), (round(ci_lower, 4), round(ci_upper, 4))


def run_ablation_study(
    texts: list[str],
    probs_list: list[dict[str, float]],
    human_ratings: np.ndarray,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate Spearman correlation across ablated estimator configurations.

    Configurations:
    1. Model-only       (w_model=1.0, w_lex=0.0, w_punct=0.0)
    2. Lexical-only     (w_model=0.0, w_lex=1.0, w_punct=0.0)
    3. Punctuation-only (w_model=0.0, w_lex=0.0, w_punct=1.0)
    4. Model + Lexical  (w_model=0.625, w_lex=0.375, w_punct=0.0)
    5. Full Estimator   (w_model=0.5, w_lex=0.3, w_punct=0.2)
    """
    ablation_weights = {
        "model_only": {"model": 1.0, "lexical": 0.0, "punctuation": 0.0},
        "lexical_only": {"model": 0.0, "lexical": 1.0, "punctuation": 0.0},
        "punctuation_only": {"model": 0.0, "lexical": 0.0, "punctuation": 1.0},
        "model_plus_lexical": {"model": 0.625, "lexical": 0.375, "punctuation": 0.0},
        "full_estimator": {"model": 0.5, "lexical": 0.3, "punctuation": 0.2},
    }

    results: dict[str, Any] = {}

    for name, w in ablation_weights.items():
        override = {"weights": w}
        scores = np.array([
            estimate_intensity(t, p, thresholds=thresholds, config_override=override)["intensity"]
            for t, p in zip(texts, probs_list)
        ])

        corr, p_val, (ci_lo, ci_hi) = compute_bootstrap_spearman_ci(human_ratings, scores)
        results[name] = {
            "weights": w,
            "spearman_rho": round(corr, 4),
            "p_value": float(f"{p_val:.4e}"),
            "bootstrap_95_ci": [ci_lo, ci_hi],
        }

    return results


def plot_intensity_scatter(
    human_ratings: np.ndarray,
    predicted_intensities: np.ndarray,
    spearman_rho: float,
    p_value: float,
    ci_range: tuple[float, float],
    output_path: str | Path = DEFAULT_FIGURE_PATH,
) -> None:
    """Render and save styled scatter plot with linear trend and correlation metrics."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)

    # Jitter human ratings slightly for visual clarity on discrete 1-5 scale
    jitter = np.random.normal(0, 0.06, size=len(human_ratings))
    x_plot = human_ratings + jitter

    ax.scatter(
        x_plot,
        predicted_intensities,
        color="#1f77b4",
        edgecolor="#0b3c5d",
        alpha=0.75,
        s=48,
        label="Messages (n=100)",
    )

    # Add linear trend line
    poly_fit = np.polyfit(human_ratings, predicted_intensities, deg=1)
    x_trend = np.linspace(1, 5, 100)
    y_trend = np.polyval(poly_fit, x_trend)
    ax.plot(x_trend, y_trend, color="#d62728", linestyle="--", linewidth=2.0, label="Trend line")

    # Annotation box
    p_text = f"p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"
    stat_box = (
        f"Spearman $\\rho$: {spearman_rho:.3f}\n"
        f"95% CI: [{ci_range[0]:.3f}, {ci_range[1]:.3f}]\n"
        f"{p_text}"
    )
    ax.text(
        0.05, 0.95, stat_box,
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8f9fa", edgecolor="#ced4da", alpha=0.9),
    )

    ax.set_title("Expression Intensity Validation: Human Ratings vs. Estimator Scores", fontsize=13, pad=15)
    ax.set_xlabel("Human Intensity Rating (1: Barely Expressed to 5: Extremely Strong)", fontsize=11, labelpad=10)
    ax.set_ylabel("Predicted Expression Intensity (0.0 to 1.0)", fontsize=11, labelpad=10)
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="lower right", frameon=True)

    plt.tight_layout()
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"[*] Validation scatter plot saved to: {out.resolve()}")


def _get_or_compute_test_probabilities(
    texts: list[str],
) -> tuple[list[dict[str, float]], dict[str, float] | None]:
    """Retrieve test probabilities from RoBERTa predict or realistic fallback."""
    # Try importing predictor from predict.py
    try:
        from app.group_decision.emotion import predict
        probs = predict(texts, apply_thresholds=False)
        # Try loading thresholds
        thr_path = Path("models/roberta_emotion/thresholds.json")
        thresholds = None
        if thr_path.is_file():
            with open(thr_path, "r", encoding="utf-8") as f:
                thresholds = json.load(f).get("per_class_thresholds")
        return probs, thresholds
    except Exception:
        pass

    # Fallback heuristic probability generator based on text emotion cues
    print("[!] RoBERTa checkpoint not loaded. Using fallback lexical probabilities for demonstration.")
    probs_list = []
    for txt in texts:
        t_low = txt.lower()
        row = {c: 0.05 for c in DEFAULT_GOEMOTIONS_LABELS}
        if any(w in t_low for w in ["love", "great", "amazing", "wonderful"]):
            row["joy"] = 0.88; row["love"] = 0.82
        elif any(w in t_low for w in ["hate", "awful", "terrible", "angry"]):
            row["anger"] = 0.85; row["disgust"] = 0.70
        elif any(w in t_low for w in ["sad", "depressed", "unhappy"]):
            row["sadness"] = 0.82
        elif any(w in t_low for w in ["scared", "fear", "nervous"]):
            row["fear"] = 0.80
        elif any(w in t_low for w in ["what", "how", "why", "?"]):
            row["curiosity"] = 0.78
        else:
            row["neutral"] = 0.85
        probs_list.append(row)

    return probs_list, {c: 0.5 for c in DEFAULT_GOEMOTIONS_LABELS}


def analyze_completed_rating_sheet(
    sheet_path: str | Path = DEFAULT_SHEET_PATH,
    results_path: str | Path = DEFAULT_RESULTS_PATH,
    figure_path: str | Path = DEFAULT_FIGURE_PATH,
    demo_mode: bool = False,
) -> dict[str, Any]:
    """Execute analysis and ablation on completed human rating sheet."""
    path = Path(sheet_path)
    if not path.is_file():
        raise FileNotFoundError(f"Rating sheet not found at: {path.resolve()}. Run with --sample first.")

    df = pd.read_csv(path)
    if "human_rating" not in df.columns or "text" not in df.columns:
        raise ValueError("Rating sheet must contain 'id', 'text', and 'human_rating' columns.")

    # Check for empty ratings
    valid_mask = pd.to_numeric(df["human_rating"], errors="coerce").notnull()
    valid_df = df[valid_mask].copy()

    if len(valid_df) == 0:
        if demo_mode:
            print("[*] Demo mode: generating synthetic 1-5 human ratings based on linguistic markers...")
            synth_ratings = []
            for txt in df["text"]:
                t = str(txt)
                score = 2.0
                if any(w in t.lower() for w in ["really", "so", "very", "extremely", "love", "hate"]):
                    score += 1.5
                if "!" in t:
                    score += min(t.count("!"), 3) * 0.4
                if any(w in t.lower() for w in ["kind of", "slightly", "maybe", "a bit"]):
                    score -= 0.8
                synth_ratings.append(int(np.clip(round(score), 1, 5)))
            df["human_rating"] = synth_ratings
            valid_df = df.copy()
        else:
            print(f"[!] '{sheet_path}' has no human ratings yet. Fill in the 'human_rating' column (1-5 scale) or use --demo.")
            return {}

    valid_df["human_rating"] = valid_df["human_rating"].astype(float)
    texts = valid_df["text"].tolist()
    human_ratings = valid_df["human_rating"].to_numpy()

    print(f"[*] Running expression intensity estimation on {len(valid_df)} rated texts...")
    probs_list, thresholds = _get_or_compute_test_probabilities(texts)

    # 1. Full estimator predictions
    full_intensities = np.array([
        estimate_intensity(t, p, thresholds=thresholds)["intensity"]
        for t, p in zip(texts, probs_list)
    ])

    # 2. Spearman correlation and 95% Bootstrap CI
    spearman_rho, p_val, ci_range = compute_bootstrap_spearman_ci(human_ratings, full_intensities)

    # 3. Ablation study
    print("[*] Running component ablation study...")
    ablation_results = run_ablation_study(texts, probs_list, human_ratings, thresholds=thresholds)

    # 4. Save results to JSON
    results_payload = {
        "num_samples_evaluated": len(valid_df),
        "spearman_rho": round(spearman_rho, 4),
        "p_value": float(f"{p_val:.4e}"),
        "bootstrap_95_ci": [ci_range[0], ci_range[1]],
        "ablation_study": ablation_results,
    }

    out_res = Path(results_path)
    out_res.parent.mkdir(parents=True, exist_ok=True)
    with open(out_res, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    print(f"[+] Validation metrics saved to: {out_res.resolve()}")

    # 5. Save Scatter Plot
    plot_intensity_scatter(human_ratings, full_intensities, spearman_rho, p_val, ci_range, output_path=figure_path)

    # Print summary table to stdout
    print("\n" + "=" * 80)
    print("  WANDARAYA C3 - EXPRESSION INTENSITY VALIDATION & ABLATION RESULTS")
    print("=" * 80)
    print(f"  Samples Evaluated               : {len(valid_df)}")
    print(f"  Full Estimator Spearman rho      : {spearman_rho:.4f}")
    print(f"  Two-Sided p-value               : {p_val:.4e}")
    print(f"  Bootstrap 95% CI                : [{ci_range[0]:.4f}, {ci_range[1]:.4f}]")
    print("-" * 80)
    print(f"  {'Ablation Configuration':<25} | {'Weights (M, L, P)':<20} | {'Spearman rho':<14} | {'95% CI':<16}")
    print("-" * 80)
    for name, r in ablation_results.items():
        w_str = f"{r['weights']['model']}, {r['weights']['lexical']}, {r['weights']['punctuation']}"
        ci_str = f"[{r['bootstrap_95_ci'][0]:.3f}, {r['bootstrap_95_ci'][1]:.3f}]"
        print(f"  {name:<25} | {w_str:<20} | {r['spearman_rho']:<14.4f} | {ci_str:<16}")
    print("=" * 80 + "\n")

    return results_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expression Intensity Validation Experiment")
    parser.add_argument("--sample", action="store_true", help="Sample 100 stratified test messages for blind rating")
    parser.add_argument("--analyze", action="store_true", help="Analyze completed rating sheet and run ablation")
    parser.add_argument("--demo", action="store_true", help="Run end-to-end demo analysis with benchmark ratings")
    parser.add_argument("--sheet-path", type=str, default=str(DEFAULT_SHEET_PATH), help="Path to rating sheet CSV")
    parser.add_argument("--results-path", type=str, default=str(DEFAULT_RESULTS_PATH), help="Path to results JSON")
    parser.add_argument("--figure-path", type=str, default=str(DEFAULT_FIGURE_PATH), help="Path to scatter plot")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.sample and not args.analyze and not args.demo:
        # Default workflow: sample if sheet doesn't exist, otherwise analyze
        if not Path(args.sheet_path).is_file():
            print("[*] No rating sheet found. Generating blind rating sheet...")
            sample_stratified_evaluation_set(output_path=args.sheet_path)
        else:
            print("[*] Existing rating sheet found. Running analysis...")
            analyze_completed_rating_sheet(
                sheet_path=args.sheet_path,
                results_path=args.results_path,
                figure_path=args.figure_path,
                demo_mode=False,
            )
        return

    if args.sample:
        sample_stratified_evaluation_set(output_path=args.sheet_path)

    if args.analyze:
        analyze_completed_rating_sheet(
            sheet_path=args.sheet_path,
            results_path=args.results_path,
            figure_path=args.figure_path,
            demo_mode=False,
        )

    if args.demo:
        if not Path(args.sheet_path).is_file():
            sample_stratified_evaluation_set(output_path=args.sheet_path)
        analyze_completed_rating_sheet(
            sheet_path=args.sheet_path,
            results_path=args.results_path,
            figure_path=args.figure_path,
            demo_mode=True,
        )


if __name__ == "__main__":
    main()
