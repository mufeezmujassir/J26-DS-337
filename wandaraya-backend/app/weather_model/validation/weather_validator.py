from dataclasses import dataclass

import pandas as pd


@dataclass
class WeatherValidationReport:
    rainfall_rows: int
    temperature_rows: int

    rainfall_missing: int
    temperature_min_missing: int
    temperature_max_missing: int

    negative_rainfall: int
    invalid_temperature_order: int

    rainfall_duplicates: int
    temperature_duplicates: int

    rainfall_station_count: int
    temperature_station_count: int


class WeatherValidator:

    @staticmethod
    def validate(
        rainfall: pd.DataFrame,
        temperature: pd.DataFrame,
    ) -> WeatherValidationReport:

        negative_rainfall = int(
            (rainfall["rainfall_mm"] < 0)
            .fillna(False)
            .sum()
        )

        invalid_temperature_order = int(
            (
                temperature["temperature_min_c"]
                >
                temperature["temperature_max_c"]
            )
            .fillna(False)
            .sum()
        )

        rainfall_duplicates = int(
            rainfall.duplicated(
                subset=["station_name", "date"]
            ).sum()
        )

        temperature_duplicates = int(
            temperature.duplicated(
                subset=["station_name", "date"]
            ).sum()
        )

        return WeatherValidationReport(
            rainfall_rows=len(rainfall),
            temperature_rows=len(temperature),

            rainfall_missing=int(
                rainfall["rainfall_mm"].isna().sum()
            ),

            temperature_min_missing=int(
                temperature["temperature_min_c"]
                .isna()
                .sum()
            ),

            temperature_max_missing=int(
                temperature["temperature_max_c"]
                .isna()
                .sum()
            ),

            negative_rainfall=negative_rainfall,

            invalid_temperature_order=(
                invalid_temperature_order
            ),

            rainfall_duplicates=rainfall_duplicates,

            temperature_duplicates=(
                temperature_duplicates
            ),

            rainfall_station_count=int(
                rainfall["station_name"].nunique()
            ),

            temperature_station_count=int(
                temperature["station_name"].nunique()
            ),
        )