from __future__ import annotations

import pandas as pd


class WeatherCoverageReporter:

    def station_coverage(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        coverage = (
            df
            .groupby(
                [
                    "station_id",
                    "station_name",
                ],
                dropna=False,
            )
            .agg(
                start_date=(
                    "observation_date",
                    "min",
                ),
                end_date=(
                    "observation_date",
                    "max",
                ),
                months=(
                    "observation_date",
                    "nunique",
                ),
                rainfall_count=(
                    "rainfall_mm",
                    "count",
                ),
                temp_min_count=(
                    "temperature_min_c",
                    "count",
                ),
                temp_max_count=(
                    "temperature_max_c",
                    "count",
                ),
            )
            .reset_index()
        )

        return coverage


    def district_coverage(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        resolved = df[
            df["district_id"].notna()
        ].copy()

        coverage = (
            resolved
            .groupby(
                [
                    "district_id",
                    "district_name",
                ],
                dropna=False,
            )
            .agg(
                start_date=(
                    "observation_date",
                    "min",
                ),
                end_date=(
                    "observation_date",
                    "max",
                ),
                months=(
                    "observation_date",
                    "nunique",
                ),
                stations=(
                    "station_id",
                    "nunique",
                ),
                rainfall_count=(
                    "rainfall_mm",
                    "count",
                ),
                temp_min_count=(
                    "temperature_min_c",
                    "count",
                ),
                temp_max_count=(
                    "temperature_max_c",
                    "count",
                ),
            )
            .reset_index()
        )

        return coverage

    def add_coverage_percentages(
        self,
        coverage: pd.DataFrame,
    ) -> pd.DataFrame:
        result = coverage.copy()
        
        result["rainfall_coverage_pct"] = (
                result["rainfall_count"]
                / result["months"]
                * 100
            ).round(2)
        
        result["temp_min_coverage_pct"] = (
                result["temp_min_count"]
                / result["months"]
                * 100
            ).round(2)
        
        result["temp_max_coverage_pct"] = (
                result["temp_max_count"]
                / result["months"]
                * 100
            ).round(2)
        
        return result

    