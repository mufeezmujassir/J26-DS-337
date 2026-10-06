from __future__ import annotations
import pandas as pd


def aggregate_district_monthly(
    df: pd.DataFrame,
) -> pd.DataFrame:

    required_columns = {
        "district_id",
        "station_id",
        "observation_date",
        "rainfall_mm",
        "temperature_min_c",
        "temperature_max_c",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            "District aggregation requires columns: "
            f"{sorted(missing_columns)}"
        )

    working = df.copy()
    working["observation_date"] = pd.to_datetime(
        working["observation_date"],
        errors="coerce",
    )

    working = working[
        working["district_id"].notna()
        & working["observation_date"].notna()
    ].copy()

    working[
        "temperature_avg_c"
    ] = (
        working[
            "temperature_min_c"
        ]
        +
        working[
            "temperature_max_c"
        ]
    ) / 2

    group_columns = ["district_id", "observation_date"]
    if "district_name" in working.columns:
        group_columns.insert(1, "district_name")

    aggregated = working.groupby(group_columns, as_index=False).agg(
        rainfall_mm=("rainfall_mm", "mean"),
        temperature_min_c=("temperature_min_c", "mean"),
        temperature_max_c=("temperature_max_c", "mean"),
        temperature_avg_c=("temperature_avg_c", "mean"),
        station_count=("station_id", "nunique"),
        rainfall_station_count=(
            "rainfall_mm",
            lambda values: int(values.notna().sum()),
        ),
        temperature_station_count=(
            "temperature_avg_c",
            lambda values: int(values.notna().sum()),
        ),
    )

    return aggregated.sort_values(group_columns).reset_index(drop=True)
