import pandas as pd


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