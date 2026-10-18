from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class WeatherQualitySummary:
    rainfall_missing: int
    temperature_min_missing: int
    temperature_max_missing: int

    rainfall_stations_with_missing: int
    temperature_stations_with_missing: int

    rainfall_expected_records: int
    rainfall_available_records: int

    temperature_expected_records: int
    temperature_available_records: int


class WeatherQualityAnalyzer:

    @staticmethod
    def rainfall_missing_report(
        rainfall: pd.DataFrame,
    ) -> pd.DataFrame:

        missing = rainfall[
            rainfall["rainfall_mm"].isna()
        ].copy()

        return (
            missing[
                [
                    "station_name",
                    "yyyy",
                    "month",
                    "date",
                    "source_file",
                ]
            ]
            .sort_values(
                ["station_name", "date"]
            )
            .reset_index(drop=True)
        )

    @staticmethod
    def temperature_missing_report(
        temperature: pd.DataFrame,
    ) -> pd.DataFrame:

        missing = temperature[
            temperature[
                [
                    "temperature_min_c",
                    "temperature_max_c",
                ]
            ]
            .isna()
            .any(axis=1)
        ].copy()

        columns = [
            "station_name",
            "yyyy",
            "month",
            "date",
            "temperature_min_c",
            "temperature_max_c",
            "temperature_avg_c",
            "source_file",
        ]

        return (
            missing[columns]
            .sort_values(
                ["station_name", "date"]
            )
            .reset_index(drop=True)
        )

    @staticmethod
    def rainfall_station_summary(
        rainfall: pd.DataFrame,
    ) -> pd.DataFrame:

        summary = (
            rainfall
            .groupby("station_name")
            .agg(
                first_date=("date", "min"),
                last_date=("date", "max"),
                records=("date", "size"),
                available_rainfall=(
                    "rainfall_mm",
                    "count",
                ),
                missing_rainfall=(
                    "rainfall_mm",
                    lambda x: x.isna().sum(),
                ),
            )
            .reset_index()
        )

        summary["coverage_pct"] = (
            summary["available_rainfall"]
            / summary["records"]
            * 100
        ).round(2)

        return summary

    @staticmethod
    def temperature_station_summary(
        temperature: pd.DataFrame,
    ) -> pd.DataFrame:

        summary = (
            temperature
            .groupby("station_name")
            .agg(
                first_date=("date", "min"),
                last_date=("date", "max"),
                records=("date", "size"),

                available_min=(
                    "temperature_min_c",
                    "count",
                ),

                available_max=(
                    "temperature_max_c",
                    "count",
                ),

                missing_min=(
                    "temperature_min_c",
                    lambda x: x.isna().sum(),
                ),

                missing_max=(
                    "temperature_max_c",
                    lambda x: x.isna().sum(),
                ),
            )
            .reset_index()
        )

        summary["min_coverage_pct"] = (
            summary["available_min"]
            / summary["records"]
            * 100
        ).round(2)

        summary["max_coverage_pct"] = (
            summary["available_max"]
            / summary["records"]
            * 100
        ).round(2)

        return summary

    @staticmethod
    def monthly_coverage(
        df: pd.DataFrame,
        value_column: str,
    ) -> pd.DataFrame:

        result = (
            df.assign(
                available=df[value_column].notna()
            )
            .groupby(["yyyy", "month"])
            .agg(
                stations=("station_name", "nunique"),
                observations=("date", "size"),
                available=("available", "sum"),
            )
            .reset_index()
        )

        result["missing"] = (
            result["observations"]
            - result["available"]
        )

        result["coverage_pct"] = (
            result["available"]
            / result["observations"]
            * 100
        ).round(2)

        return result

    @staticmethod
    def compare_station_sources(
        rainfall: pd.DataFrame,
        temperature: pd.DataFrame,
    ) -> dict:

        rainfall_stations = set(
            rainfall["station_name"]
            .dropna()
            .unique()
        )

        temperature_stations = set(
            temperature["station_name"]
            .dropna()
            .unique()
        )

        common = (
            rainfall_stations
            & temperature_stations
        )

        rainfall_only = (
            rainfall_stations
            - temperature_stations
        )

        temperature_only = (
            temperature_stations
            - rainfall_stations
        )

        return {
            "rainfall_stations": sorted(
                rainfall_stations
            ),
            "temperature_stations": sorted(
                temperature_stations
            ),
            "common_stations": sorted(common),
            "rainfall_only": sorted(
                rainfall_only
            ),
            "temperature_only": sorted(
                temperature_only
            ),
            "rainfall_station_count": len(
                rainfall_stations
            ),
            "temperature_station_count": len(
                temperature_stations
            ),
            "common_station_count": len(common),
        }

    @staticmethod
    def coordinate_report(
        rainfall: pd.DataFrame,
        temperature: pd.DataFrame,
    ) -> dict:

        rainfall_station_coords = (
            rainfall[
                [
                    "station_name",
                    "latitude",
                    "longitude",
                ]
            ]
            .drop_duplicates(
                subset=["station_name"]
            )
        )

        temperature_station_coords = (
            temperature[
                [
                    "station_name",
                    "latitude",
                    "longitude",
                ]
            ]
            .drop_duplicates(
                subset=["station_name"]
            )
        )

        rainfall_missing_coords = (
            rainfall_station_coords[
                rainfall_station_coords[
                    ["latitude", "longitude"]
                ]
                .isna()
                .any(axis=1)
            ]
        )

        temperature_missing_coords = (
            temperature_station_coords[
                temperature_station_coords[
                    ["latitude", "longitude"]
                ]
                .isna()
                .any(axis=1)
            ]
        )

        return {
            "rainfall_missing_coordinates":
                rainfall_missing_coords[
                    "station_name"
                ].tolist(),

            "temperature_missing_coordinates":
                temperature_missing_coords[
                    "station_name"
                ].tolist(),
        }