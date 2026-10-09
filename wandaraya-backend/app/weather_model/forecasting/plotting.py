from pathlib import Path
import pandas as pd

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt


def plot_forecast_comparison(
    actual,
    prophet_predictions,
    baseline_predictions,
    title,
    output_path,
):
    actual = actual.copy()
    actual["ds"] = pd.to_datetime(actual["ds"])

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        actual["ds"],
        actual["y"],
        marker="o",
        label="Actual",
    )

    ax.plot(
        prophet_predictions["ds"],
        prophet_predictions["yhat"],
        marker="s",
        label="Prophet",
    )

    ax.plot(
        baseline_predictions["ds"],
        baseline_predictions["yhat"],
        marker="^",
        label="Seasonal Naive",
    )

    ax.set_title(title)
    ax.set_xlabel("Month")
    ax.set_ylabel("Weather value")
    ax.legend()
    ax.grid(alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(output_path, dpi=180)
    plt.close(fig)
