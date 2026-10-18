import pandas as pd


def aggregate_district_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate resolved station-month readings without summing rainfall."""
    required = {
        "district_id", "station_id", "observation_date", "rainfall_mm",
        "temperature_min_c", "temperature_max_c",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"District aggregation is missing columns: {sorted(missing)}")

    working = df.copy()
    working["observation_date"] = pd.to_datetime(
        working["observation_date"], errors="coerce"
    )
    working = working[
        working["district_id"].notna() & working["observation_date"].notna()
    ].copy()
    working["temperature_avg_c"] = (
        working["temperature_min_c"] + working["temperature_max_c"]
    ) / 2

    group_columns = ["district_id", "observation_date"]
    if "district_name" in working.columns:
        group_columns.insert(1, "district_name")

    result = working.groupby(group_columns, as_index=False).agg(
        rainfall_mm=("rainfall_mm", "mean"),
        temperature_min_c=("temperature_min_c", "mean"),
        temperature_max_c=("temperature_max_c", "mean"),
        temperature_avg_c=("temperature_avg_c", "mean"),
        station_count=("station_id", "nunique"),
        rainfall_station_count=("rainfall_mm", lambda values: int(values.notna().sum())),
        temperature_station_count=(
            "temperature_avg_c", lambda values: int(values.notna().sum())
        ),
    )
    return result.sort_values(group_columns).reset_index(drop=True)


class MonthlyWeatherAggregator:

    @staticmethod
    def aggregate_rainfall(
        rainfall: pd.DataFrame,
    ) -> pd.DataFrame:

        return (
            rainfall
            .groupby(
                ["district_id", "yyyy", "month"],
                as_index=False,
            )
            .agg(
                rainfall_mm=(
                    "rainfall_mm",
                    "mean",
                ),
                rainfall_station_count=(
                    "station_name",
                    "nunique",
                ),
            )
        )

    @staticmethod
    def aggregate_temperature(
        temperature: pd.DataFrame,
    ) -> pd.DataFrame:

        return (
            temperature
            .groupby(
                ["district_id", "yyyy", "month"],
                as_index=False,
            )
            .agg(
                temperature_min_c=(
                    "temperature_min_c",
                    "mean",
                ),
                temperature_max_c=(
                    "temperature_max_c",
                    "mean",
                ),
                temperature_avg_c=(
                    "temperature_avg_c",
                    "mean",
                ),
                temperature_station_count=(
                    "station_name",
                    "nunique",
                ),
            )
        )
