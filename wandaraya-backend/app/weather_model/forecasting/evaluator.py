import numpy as np
import pandas as pd

from sklearn.metrics import(
    mean_squared_error,
    mean_absolute_error,
)

def evaluate_forecast(
        actual:pd.DataFrame,
        predictions:pd.DataFrame,
        model_name:str,
):
    merged = actual[["ds", "y"]].merge(
        predictions[["ds", "yhat"]],
        on="ds",
        how="inner",
        validate="one_to_one",
    )

    merged = merged.replace(
        [np.inf, -np.inf], np.nan
    ).dropna(subset=["y", "yhat"])

    if merged.empty:
        raise ValueError(
            f"No valid predictions for {model_name}"
        )

    mae = mean_absolute_error(
        merged["y"], merged["yhat"]
    )

    rmse = np.sqrt(
        mean_squared_error(
            merged["y"], merged["yhat"]
        )
    )

    return {
        "model": model_name,
        "mae": round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "evaluated_months": len(merged),
    }
