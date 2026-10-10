from __future__ import annotations

from pathlib import Path
import pandas as pd

class WeatherForecastDataLoader:

    def __init__(
            self,
            base_dir="/app/data/weather/modeling/prophet",

    ):
        self.base_dir = Path(base_dir)


    def load(
            self,
            district_id:int,
            target:str,
            split:str="full",

    )->pd.DataFrame:

        allowed_targets = ["rainfall_mm", "temperature_min_c", "temperature_max_c"]
        allowed_splits={"full", "train", "test"}

        if target not in allowed_targets:
            raise ValueError(f"Invalid target: {target}. Allowed targets are: {allowed_targets}")

        if split not in allowed_splits:
            raise ValueError(f"Invalid split: {split}. Allowed splits are: {allowed_splits}")

        path=(
            self.base_dir/target/f"district_{district_id}_{split}.csv"
        )

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        df=pd.read_csv(path)

        if not {"ds", "y"}.issubset(df.columns):
            raise ValueError(f"DataFrame must contain 'ds' and 'y' columns. Found columns: {df.columns}")

        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = pd.to_numeric(
            df["y"], errors="coerce"
        )

        df = df.sort_values("ds").reset_index(
            drop=True
        )

        if df["ds"].duplicated().any():
            raise ValueError("Duplicate dates detected")

        if target == "rainfall_mm":
            if (df["y"].dropna() < 0).any():
                raise ValueError("Negative rainfall")

        return df

