"""Generate report-ready Component 1 data-analysis figures from verified data."""
from __future__ import annotations

import argparse
import csv
import subprocess
from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / "output" / "component1_data_analysis"
EVALUATION = ROOT / "data/weather/modeling/nasa_power/reports/daily_prophet_evaluation.csv"

GREEN = "#0F766E"
LIGHT_GREEN = "#5FA89F"
GOLD = "#D69E2E"
BLUE = "#2C7FB8"
RED = "#C2413B"
PURPLE = "#7551A6"
GREY = "#68737D"
GRID = "#D8DEE3"


def query_csv(sql: str) -> pd.DataFrame:
    command = [
        "docker", "exec", "wandaraya-postgres", "psql", "-U", "postgres",
        "-d", "wandaraya", "--csv", "-c", sql,
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return pd.read_csv(StringIO(completed.stdout))


def finish(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def clean_generated_outputs(output: Path) -> None:
    """Remove only files owned by this generator, leaving unrelated user files intact."""
    generated_patterns = ("figure_*.png", "*.csv", "REPORT_CAPTIONS_AND_ANALYSIS.md")
    for pattern in generated_patterns:
        for path in output.glob(pattern):
            if path.is_file():
                path.unlink()


def configure_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
        "axes.edgecolor": GREY,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.alpha": 0.75,
        "legend.frameon": False,
        "figure.titlesize": 15,
    })


def attraction_theme_figure(output: Path) -> pd.DataFrame:
    themes = query_csv("""
        SELECT c.name AS theme, COUNT(a.id)::int AS attractions
        FROM categories c
        LEFT JOIN attraction_categories ac ON ac.category_id = c.id
        LEFT JOIN attractions a ON a.id = ac.attraction_id AND a.is_active
        GROUP BY c.name ORDER BY attractions DESC, c.name
    """)
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    bars = ax.barh(themes["theme"], themes["attractions"], color=GREEN)
    ax.invert_yaxis()
    ax.set_title("Active Attractions by Tourism Theme")
    ax.set_xlabel("Number of active attractions")
    ax.set_ylabel("Tourism theme")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.bar_label(bars, padding=4, fontsize=9)
    ax.set_xlim(0, max(themes["attractions"].max() * 1.14, 1))
    finish(fig, output / "figure_01_attractions_by_theme.png")
    return themes


def district_coverage_figure(output: Path) -> pd.DataFrame:
    districts = query_csv("""
        SELECT d.name AS district, COUNT(a.id)::int AS attractions
        FROM districts d
        LEFT JOIN attractions a ON a.district_id = d.id AND a.is_active
        GROUP BY d.id, d.name ORDER BY attractions DESC, district
    """)
    fig, ax = plt.subplots(figsize=(8.2, 8.4))
    colors = [GREEN if value > 0 else "#BCC4CA" for value in districts["attractions"]]
    bars = ax.barh(districts["district"], districts["attractions"], color=colors)
    ax.invert_yaxis()
    ax.set_title("Geographic Coverage of the Verified Attraction Catalogue")
    ax.set_xlabel("Number of active attractions")
    ax.set_ylabel("District")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_xlim(0, districts["attractions"].max() * 1.13)
    finish(fig, output / "figure_02_attractions_by_district.png")
    return districts


def data_quality_figure(output: Path) -> pd.DataFrame:
    quality = query_csv("""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE NULLIF(BTRIM(description), '') IS NOT NULL)::int AS description,
            COUNT(*) FILTER (WHERE district_id IS NOT NULL)::int AS district,
            COUNT(*) FILTER (WHERE latitude IS NOT NULL AND longitude IS NOT NULL)::int AS coordinates,
            COUNT(*) FILTER (WHERE google_place_id IS NOT NULL)::int AS google_identity,
            COUNT(*) FILTER (WHERE rating IS NOT NULL)::int AS rating,
            COUNT(*) FILTER (WHERE review_count IS NOT NULL)::int AS review_count,
            COUNT(*) FILTER (WHERE opening_hours IS NOT NULL AND opening_hours::text NOT IN ('null', '{}', '[]'))::int AS opening_hours,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM attraction_images ai WHERE ai.attraction_id = attractions.id
            ))::int AS image
        FROM attractions WHERE is_active
    """)
    total = int(quality.loc[0, "total"])
    fields = ["description", "district", "coordinates", "google_identity", "rating", "review_count", "opening_hours", "image"]
    labels = ["Description", "District", "Coordinates", "Google identity", "Rating", "Review count", "Opening hours", "Image"]
    counts = quality.loc[0, fields].astype(int).to_numpy()
    percentages = counts / total * 100
    frame = pd.DataFrame({"field": labels, "complete_records": counts, "total_records": total, "coverage_pct": percentages})

    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    colors = [GREEN if value >= 95 else GOLD if value >= 70 else BLUE for value in percentages]
    bars = ax.barh(labels, percentages, color=colors)
    ax.invert_yaxis()
    ax.set_title(f"Data Completeness Across {total:,} Active Attractions")
    ax.set_xlabel("Coverage (%)")
    ax.set_xlim(0, 108)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    for bar, count, pct in zip(bars, counts, percentages, strict=True):
        ax.text(pct + 1.2, bar.get_y() + bar.get_height() / 2, f"{count:,} ({pct:.1f}%)", va="center", fontsize=9)
    finish(fig, output / "figure_03_data_quality_coverage.png")
    return frame


def ingestion_outcomes_figure(output: Path) -> pd.DataFrame:
    outcomes = query_csv("""
        SELECT validation_status AS status, COUNT(*)::int AS records
        FROM tourism_source_staging
        WHERE source_provider = 'dayouting.lk'
        GROUP BY validation_status
        ORDER BY records DESC, status
    """)
    label_map = {
        "promoted": "Promoted as new",
        "linked": "Linked to existing",
        "pending_manual_identity_review": "Manual identity review",
        "pending_content_review": "Content review",
        "pending_category_review": "Category review",
        "rejected_non_attraction_name": "Rejected non-attraction",
    }
    outcomes["label"] = outcomes["status"].map(label_map).fillna(outcomes["status"].str.replace("_", " ").str.title())
    total = int(outcomes["records"].sum())
    accepted = outcomes["status"].isin(["promoted", "linked"])
    colors = [GREEN if is_accepted else RED if status.startswith("rejected") else GOLD for is_accepted, status in zip(accepted, outcomes["status"], strict=True)]

    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    bars = ax.barh(outcomes["label"], outcomes["records"], color=colors)
    ax.invert_yaxis()
    ax.set_title(f"DayOuting Source Verification Outcomes (n={total:,})")
    ax.set_xlabel("Number of staged records")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.bar_label(bars, labels=[f"{value:,} ({value / total * 100:.1f}%)" for value in outcomes["records"]], padding=4, fontsize=9)
    ax.set_xlim(0, max(outcomes["records"].max() * 1.22, 1))
    finish(fig, output / "figure_04_ingestion_verification_outcomes.png")
    return outcomes[["status", "label", "records"]]


def attraction_correlation_figure(output: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    observations = query_csv("""
        SELECT
            a.id,
            a.rating,
            LN(1 + COALESCE(a.review_count, 0)) AS log_review_count,
            LENGTH(COALESCE(a.description, ''))::double precision AS description_length,
            COALESCE(cat.category_count, 0)::double precision AS category_count,
            COALESCE(img.image_count, 0)::double precision AS image_count,
            CASE WHEN a.opening_hours IS NOT NULL AND a.opening_hours::text NOT IN ('null', '{}', '[]') THEN 1.0 ELSE 0.0 END AS has_opening_hours,
            CASE WHEN a.google_place_id IS NOT NULL THEN 1.0 ELSE 0.0 END AS has_google_identity,
            CASE WHEN src.attraction_id IS NOT NULL THEN 1.0 ELSE 0.0 END AS has_dayouting_source
        FROM attractions a
        LEFT JOIN (
            SELECT attraction_id, COUNT(*) AS category_count
            FROM attraction_categories GROUP BY attraction_id
        ) cat ON cat.attraction_id = a.id
        LEFT JOIN (
            SELECT attraction_id, COUNT(*) AS image_count
            FROM attraction_images GROUP BY attraction_id
        ) img ON img.attraction_id = a.id
        LEFT JOIN (
            SELECT DISTINCT attraction_id
            FROM attraction_source_references
            WHERE source_provider = 'dayouting.lk'
        ) src ON src.attraction_id = a.id
        WHERE a.is_active
    """)
    labels = {
        "rating": "Rating",
        "log_review_count": "Log reviews",
        "description_length": "Description length",
        "image_count": "Image count",
        "has_opening_hours": "Opening hours",
        "has_dayouting_source": "DayOuting source",
    }
    numeric = observations[list(labels)].rename(columns=labels)
    correlation = numeric.corr(method="pearson", min_periods=30)

    fig, ax = plt.subplots(figsize=(8.6, 7.2))
    image = ax.imshow(correlation, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(correlation.columns)), correlation.columns, rotation=42, ha="right")
    ax.set_yticks(range(len(correlation.index)), correlation.index)
    for row in range(len(correlation.index)):
        for column in range(len(correlation.columns)):
            value = correlation.iloc[row, column]
            color = "white" if abs(value) >= 0.55 else "#263238"
            ax.text(column, row, "—" if np.isnan(value) else f"{value:.2f}", ha="center", va="center", color=color, fontsize=9)
    ax.set_title("Correlation Heatmap of Attraction Metadata Features")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.82)
    colorbar.set_label("Pearson correlation coefficient")
    fig.tight_layout()
    finish(fig, output / "figure_05_attraction_feature_correlation_heatmap.png")
    return observations, correlation


def rating_popularity_figure(output: Path, observations: pd.DataFrame) -> pd.DataFrame:
    plotted = observations.dropna(subset=["rating"]).copy()
    plotted["review_count"] = np.expm1(plotted["log_review_count"])
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    scatter = ax.scatter(
        plotted["review_count"], plotted["rating"],
        c=np.log1p(plotted["description_length"]), cmap="viridis", alpha=0.55, s=24, edgecolors="none",
    )
    ax.set_xscale("symlog", linthresh=1)
    ax.set_title("Visitor Rating and Review Volume of Verified Attractions")
    ax.set_xlabel("Google review count (log scale)")
    ax.set_ylabel("Visitor rating (0–5)")
    ax.set_ylim(max(0, float(plotted["rating"].min()) - 0.25), 5.15)
    colorbar = fig.colorbar(scatter, ax=ax)
    colorbar.set_label("Log description length")
    ax.grid(True, alpha=0.45)
    finish(fig, output / "figure_06_rating_vs_review_volume.png")
    return plotted[["id", "rating", "review_count", "category_count", "description_length", "image_count"]]


def forecast_performance_figure(output: Path, evaluation: pd.DataFrame) -> pd.DataFrame:
    summary = (
        evaluation.groupby("target", as_index=False)
        .agg(mean_mae=("test_mae", "mean"), mean_rmse=("test_rmse", "mean"), mean_bias=("test_bias", "mean"))
    )
    labels = {
        "rainfall_mm": "Rainfall",
        "temperature_min_c": "Minimum temperature",
        "temperature_max_c": "Maximum temperature",
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.7), gridspec_kw={"width_ratios": [1, 1.55]})

    rainfall = summary[summary["target"] == "rainfall_mm"].iloc[0]
    bars = axes[0].bar(["MAE", "RMSE"], [rainfall.mean_mae, rainfall.mean_rmse], color=[GREEN, GOLD])
    axes[0].bar_label(bars, fmt="%.2f", padding=4)
    axes[0].set_title("Rainfall forecast error")
    axes[0].set_ylabel("Error (mm/day)")
    axes[0].grid(axis="y")
    axes[0].grid(axis="x", visible=False)

    temperature = summary[summary["target"].str.startswith("temperature")].copy()
    temperature["label"] = temperature["target"].map(labels)
    x = np.arange(len(temperature))
    width = 0.34
    mae = axes[1].bar(x - width / 2, temperature["mean_mae"], width, label="MAE", color=GREEN)
    rmse = axes[1].bar(x + width / 2, temperature["mean_rmse"], width, label="RMSE", color=GOLD)
    axes[1].bar_label(mae, fmt="%.2f", padding=3, fontsize=9)
    axes[1].bar_label(rmse, fmt="%.2f", padding=3, fontsize=9)
    axes[1].set_xticks(x, temperature["label"])
    axes[1].set_title("Temperature forecast error")
    axes[1].set_ylabel("Error (°C)")
    axes[1].legend()
    axes[1].grid(axis="y")
    axes[1].grid(axis="x", visible=False)
    fig.suptitle("Daily Prophet Model Performance on the 2025 Holdout Set")
    fig.tight_layout()
    finish(fig, output / "figure_07_prophet_test_performance.png")
    return summary


def rain_classification_figure(output: Path, evaluation: pd.DataFrame) -> pd.DataFrame:
    rainfall = evaluation[evaluation["target"] == "rainfall_mm"].copy()
    columns = [
        "test_rain_event_accuracy", "test_rain_event_precision",
        "test_rain_event_recall", "test_rain_event_f1",
    ]
    labels = ["Accuracy", "Precision", "Recall", "F1-score"]
    values = [rainfall[column].dropna().to_numpy() for column in columns]
    means = [float(np.mean(value)) for value in values]
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    box = ax.boxplot(values, tick_labels=labels, patch_artist=True, widths=0.58, showfliers=True)
    for patch in box["boxes"]:
        patch.set_facecolor(LIGHT_GREEN)
        patch.set_alpha(0.75)
    for median in box["medians"]:
        median.set_color(GREEN)
        median.set_linewidth(2)
    ax.scatter(np.arange(1, 5), means, color=RED, marker="D", s=38, label="District mean", zorder=4)
    for index, mean in enumerate(means, 1):
        ax.text(index, mean + 0.035, f"{mean:.3f}", ha="center", va="bottom", fontsize=9)
    ax.set_title("Rain-Event Classification Across 25 Districts")
    ax.set_ylabel("Metric value")
    ax.set_ylim(0.2, 1.02)
    ax.legend(loc="lower right")
    ax.grid(axis="y")
    ax.grid(axis="x", visible=False)
    finish(fig, output / "figure_08_rain_event_metrics.png")
    return rainfall[["district_id", "district_name", *columns, "test_rain_prediction_threshold_mm"]]


def galle_seasonality_figure(output: Path) -> pd.DataFrame:
    seasonality = query_csv("""
        SELECT month,
               (feature_vector_json->>'rainfall_mean_mm')::double precision AS rainfall_mean_mm,
               (feature_vector_json->>'temp_mean_c')::double precision AS temperature_mean_c,
               (feature_vector_json->>'relative_humidity_mean_pct')::double precision AS humidity_mean_pct,
               relative_rainfall_favorability,
               temperature_comfort_index,
               humidity_comfort_index,
               rainfall_reliability_index,
               seasonality_uncertainty_score,
               baseline_b_multivar_score
        FROM climate_seasonality_features
        WHERE district_id = 78
        ORDER BY month
    """)
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.4), sharex=True)
    x = seasonality["month"].to_numpy()

    axes[0].bar(x, seasonality["rainfall_mean_mm"], color=BLUE, alpha=0.82, label="Mean rainfall")
    axes[0].set_ylabel("Rainfall (mm/month)")
    axes[0].set_title("Historical monthly rainfall")
    axes[0].grid(axis="y")
    axes[0].grid(axis="x", visible=False)
    axes[0].legend(loc="upper left")

    axes[1].plot(x, seasonality["baseline_b_multivar_score"], color=GREEN, marker="o", label="Composite suitability")
    axes[1].plot(x, seasonality["relative_rainfall_favorability"], color=GOLD, marker="s", label="Rainfall favourability")
    axes[1].plot(x, seasonality["temperature_comfort_index"], color=PURPLE, marker="^", label="Temperature comfort")
    axes[1].set_ylabel("Normalized score (0–1)")
    axes[1].set_xlabel("Calendar month")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_xticks(x, month_labels)
    axes[1].grid(axis="y")
    axes[1].grid(axis="x", visible=False)
    axes[1].legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.32))
    fig.suptitle("Galle District Historical Seasonality Profile")
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    finish(fig, output / "figure_09_galle_seasonality.png")
    return seasonality


def temporal_split_figure(output: Path) -> pd.DataFrame:
    split = pd.DataFrame([
        {"partition": "Training", "start": 2010.0, "end": 2024.0, "days": 5113, "purpose": "Model fitting"},
        {"partition": "Validation", "start": 2024.0, "end": 2025.0, "days": 366, "purpose": "Threshold selection"},
        {"partition": "Testing", "start": 2025.0, "end": 2026.0, "days": 365, "purpose": "Untouched evaluation"},
    ])
    fig, ax = plt.subplots(figsize=(10.0, 3.5))
    colors = [GREEN, GOLD, BLUE]
    for row, color in zip(split.itertuples(), colors, strict=True):
        ax.barh(row.partition, row.end - row.start, left=row.start, color=color, height=0.5)
        label = f"{row.days:,} days · {row.purpose}"
        if row.partition == "Training":
            ax.text((row.start + row.end) / 2, row.partition, label, ha="center", va="center", color="white", fontsize=9)
        else:
            ax.text(row.start - 0.15, row.partition, label, ha="right", va="center", color="#263238", fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(2009.5, 2026.2)
    ax.set_xticks(range(2010, 2027, 2))
    ax.set_xlabel("Calendar year")
    ax.set_title("Leakage-Safe Chronological Split for Daily Weather Modelling")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    finish(fig, output / "figure_10_weather_temporal_split.png")
    return split


def write_analysis(
    output: Path,
    themes: pd.DataFrame,
    districts: pd.DataFrame,
    quality: pd.DataFrame,
    outcomes: pd.DataFrame,
    correlation: pd.DataFrame,
    performance: pd.DataFrame,
    rain_metrics: pd.DataFrame,
    seasonality: pd.DataFrame,
) -> None:
    theme_top = themes.iloc[0]
    district_top = districts.iloc[0]
    uncovered = int((districts["attractions"] == 0).sum())
    active_total = int(quality["total_records"].iloc[0])
    accepted = int(outcomes.loc[outcomes.status.isin(["promoted", "linked"]), "records"].sum())
    staged_total = int(outcomes["records"].sum())
    rainfall = performance[performance.target == "rainfall_mm"].iloc[0]
    minimum = performance[performance.target == "temperature_min_c"].iloc[0]
    maximum = performance[performance.target == "temperature_max_c"].iloc[0]
    rain_means = rain_metrics.mean(numeric_only=True)
    best_month = seasonality.loc[seasonality.baseline_b_multivar_score.idxmax()]
    wettest_month = seasonality.loc[seasonality.rainfall_mean_mm.idxmax()]
    month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    corr_without_diagonal = correlation.where(~np.eye(len(correlation), dtype=bool)).abs()
    strongest_pair = corr_without_diagonal.stack().idxmax()
    strongest_value = correlation.loc[strongest_pair[0], strongest_pair[1]]
    text = f"""# Component 1 figures and interpretation

## Figure 1 — Active attractions by tourism theme

The verified catalogue contains **{active_total:,} active attractions**. It is dominated by **{theme_top.theme}** attractions ({int(theme_top.attractions):,} mappings), followed by **{themes.iloc[1].theme}** ({int(themes.iloc[1].attractions):,} mappings). Because attractions may carry more than one theme, these bars are category mappings rather than mutually exclusive record counts. The imbalance supports combining semantic similarity with explicit theme constraints during recommendation.

## Figure 2 — Geographic coverage

The expanded catalogue is geographically imbalanced. **{district_top.district}** contains the largest number of verified records ({int(district_top.attractions):,}), while {uncovered} districts contain no active attraction. The chart represents database coverage, not the true physical supply of tourism attractions. Candidate diversity will therefore vary by district.

## Figure 3 — Data completeness

The chart measures the availability of recommendation-critical metadata across all **{active_total:,} active attractions**. Description and district coverage should remain at 100%, while optional Google fields such as ratings, websites, and opening hours naturally have lower coverage. The system must treat missing optional values as unavailable evidence rather than inventing them.

## Figure 4 — Source verification outcomes

Of **{staged_total:,} complete DayOuting source records**, **{accepted:,} ({accepted / staged_total * 100:.1f}%)** were either promoted as verified new attractions or linked to an existing attraction. Remaining records are isolated in review states instead of being exposed to users. This is the main data-quality safeguard against junctions, locality names, duplicates, and ambiguous category assignments.

## Figure 5 — Attraction feature correlation heatmap

The strongest non-diagonal relationship is between **{strongest_pair[0]}** and **{strongest_pair[1]}** (r = **{strongest_value:.2f}**). Correlation describes association, not causation. Binary fields such as website and opening-hours availability are included as 0/1 indicators, while review count is log-transformed to reduce extreme skew.

## Figure 6 — Rating versus review volume

The scatter plot separates popularity (review volume) from satisfaction (rating). Review count uses a logarithmic axis because a small number of famous attractions have orders of magnitude more reviews. Colour represents log-transformed description length, allowing content richness to be inspected without implying that it causes higher ratings.

## Figure 7 — Daily Prophet test performance

Temperature is substantially more predictable than rainfall. On the untouched 2025 test set, minimum temperature achieved a mean MAE of **{minimum.mean_mae:.3f}°C**, while maximum temperature achieved **{maximum.mean_mae:.3f}°C**. Rainfall achieved a mean MAE of **{rainfall.mean_mae:.3f} mm/day** and RMSE of **{rainfall.mean_rmse:.3f} mm/day**. The larger rainfall RMSE indicates that high-rainfall events produce much larger errors than ordinary days. Long-range rainfall forecasts should therefore be displayed with uncertainty and used as suitability evidence rather than guaranteed exact weather.

## Figure 8 — Rain-event classification

Across 25 districts, mean rain-event precision was **{rain_means.test_rain_event_precision:.3f}**, recall was **{rain_means.test_rain_event_recall:.3f}**, F1-score was **{rain_means.test_rain_event_f1:.3f}**, and accuracy was **{rain_means.test_rain_event_accuracy:.3f}**. Precision being higher than recall means that predicted rainy days are usually credible, but some actual rainy days remain undetected. This supports conservative explanations and indoor alternatives when rainfall risk is uncertain.

## Figure 9 — Galle historical seasonality

The Galle profile shows clear month-to-month variation. **{month_names[int(best_month.month)-1]}** has the highest multi-variable suitability score ({best_month.baseline_b_multivar_score:.3f}), while **{month_names[int(wettest_month.month)-1]}** has the highest historical mean rainfall ({wettest_month.rainfall_mean_mm:.2f} mm/month). Temperature comfort remains relatively stable, so rainfall and humidity explain most of the seasonal movement. This profile represents historical climatology and must not replace a live or date-specific daily forecast.

## Figure 10 — Chronological modelling split

The chronological split prevents future information from leaking into model training. Observations from 2010–2023 are used for fitting, 2024 is used for threshold selection and validation, and 2025 remains untouched until final evaluation. This produces a more realistic estimate of future forecasting performance than a random train-test split.

## Suggested placement in the report

- Place Figures 1–6 under **Attraction Dataset — Key Insights and Data Quality**.
- Place Figure 10 under **Feature Extraction / Model Preparation**.
- Place Figures 7 and 8 under **Weather Forecasting — Modelling and Results**.
- Place Figure 9 under **Historical Seasonality — Key Insights**.
"""
    (output / "REPORT_CAPTIONS_AND_ANALYSIS.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    clean_generated_outputs(output)
    configure_style()
    evaluation = pd.read_csv(EVALUATION)

    themes = attraction_theme_figure(output)
    districts = district_coverage_figure(output)
    quality = data_quality_figure(output)
    outcomes = ingestion_outcomes_figure(output)
    observations, correlation = attraction_correlation_figure(output)
    rating_popularity = rating_popularity_figure(output, observations)
    performance = forecast_performance_figure(output, evaluation)
    rain_metrics = rain_classification_figure(output, evaluation)
    seasonality = galle_seasonality_figure(output)
    split = temporal_split_figure(output)

    tables = {
        "attractions_by_theme.csv": themes,
        "attractions_by_district.csv": districts,
        "attraction_data_quality.csv": quality,
        "dayouting_verification_outcomes.csv": outcomes,
        "attraction_feature_observations.csv": observations,
        "attraction_feature_correlations.csv": correlation.reset_index(names="feature"),
        "rating_review_analysis.csv": rating_popularity,
        "prophet_test_performance_summary.csv": performance,
        "rain_event_metrics_by_district.csv": rain_metrics,
        "galle_seasonality_features.csv": seasonality,
        "weather_temporal_split.csv": split,
    }
    for name, frame in tables.items():
        frame.to_csv(output / name, index=False, quoting=csv.QUOTE_MINIMAL)
    write_analysis(output, themes, districts, quality, outcomes, correlation, performance, rain_metrics, seasonality)
    print(f"Generated {len(list(output.glob('figure_*.png')))} figures in {output}")


if __name__ == "__main__":
    main()
