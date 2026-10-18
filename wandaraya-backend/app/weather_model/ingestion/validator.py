from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


REQUIRED_COLUMNS = [
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "observation_date",
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
    "humidity_percent",
]

MEASUREMENT_COLUMNS = [
    "rainfall_mm",
    "temperature_min_c",
    "temperature_max_c",
    "humidity_percent",
]


@dataclass
class WeatherValidationResult:
    is_valid: bool

    total_rows: int
    total_stations: int

    empty_rows: int
    missing_identity_rows: int
    rows_without_measurement: int

    duplicate_rows: int
    duplicate_groups: int

    missing_rainfall: int
    missing_temperature_min: int
    missing_temperature_max: int
    missing_humidity: int

    invalid_rainfall: int
    invalid_temperature_min: int
    invalid_temperature_max: int
    invalid_temperature_relationship: int

    invalid_latitude: int
    invalid_longitude: int

    warnings: list[str] = field(
        default_factory=list
    )

    errors: list[str] = field(
        default_factory=list
    )


class WeatherDataValidator:

    def validate(
        self,
        df: pd.DataFrame,
    ) -> WeatherValidationResult:

        errors: list[str] = []
        warnings: list[str] = []


        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                "Weather dataset missing required columns: "
                f"{missing_columns}"
            )

        working = df.copy()

 
        working["observation_date"] = (
            pd.to_datetime(
                working["observation_date"],
                errors="coerce",
            )
        )

        numeric_columns = [
            "latitude",
            "longitude",
            "rainfall_mm",
            "temperature_min_c",
            "temperature_max_c",
            "humidity_percent",
        ]

        for column in numeric_columns:
            working[column] = (
                pd.to_numeric(
                    working[column],
                    errors="coerce",
                )
            )


        empty_rows_mask = (
            working[
                REQUIRED_COLUMNS
            ]
            .isna()
            .all(axis=1)
        )

        empty_rows = int(
            empty_rows_mask.sum()
        )

        if empty_rows > 0:
            errors.append(
                f"{empty_rows} completely empty normalized "
                "weather rows detected."
            )



        station_id_missing = (
            working["station_id"].isna()
            | (
                working["station_id"]
                .astype("string")
                .str.strip()
                .eq("")
            )
        )

        station_name_missing = (
            working["station_name"].isna()
            | (
                working["station_name"]
                .astype("string")
                .str.strip()
                .eq("")
            )
        )

        date_missing = (
            working["observation_date"].isna()
        )

        missing_identity_mask = (
            station_id_missing
            | station_name_missing
            | date_missing
        )

        missing_identity_rows = int(
            missing_identity_mask.sum()
        )

        if missing_identity_rows > 0:
            errors.append(
                f"{missing_identity_rows} rows are missing "
                "station identity or observation date."
            )


        rows_without_measurement_mask = (
            working[
                MEASUREMENT_COLUMNS
            ]
            .isna()
            .all(axis=1)
        )

        rows_without_measurement = int(
            rows_without_measurement_mask.sum()
        )

        if rows_without_measurement > 0:
            errors.append(
                f"{rows_without_measurement} rows contain "
                "no weather measurement."
            )



        # One normalized row represents one station's observation for a month.
        # Complementary source values must have been coalesced before validation.
        duplicate_subset = [
            "station_id",
            "observation_date",
        ]

        duplicate_mask = (
            working.duplicated(
                subset=duplicate_subset,
                keep=False,
            )
        )

        duplicate_rows = int(
            duplicate_mask.sum()
        )

        if duplicate_rows > 0:

            duplicate_data = working[
                duplicate_mask
            ]

            duplicate_groups = int(
                duplicate_data
                .groupby(
                    duplicate_subset,
                    dropna=False,
                )
                .ngroups
            )

            errors.append(
                f"{duplicate_rows} duplicate station/month rows "
                f"across {duplicate_groups} groups detected."
            )

        else:
            duplicate_groups = 0

        missing_rainfall = int(
            working[
                "rainfall_mm"
            ].isna().sum()
        )

        missing_temperature_min = int(
            working[
                "temperature_min_c"
            ].isna().sum()
        )

        missing_temperature_max = int(
            working[
                "temperature_max_c"
            ].isna().sum()
        )

        missing_humidity = int(
            working[
                "humidity_percent"
            ].isna().sum()
        )


        if missing_rainfall > 0:
            warnings.append(
                f"{missing_rainfall} rows have no rainfall "
                "measurement."
            )

        if missing_temperature_min > 0:
            warnings.append(
                f"{missing_temperature_min} rows have no "
                "minimum temperature measurement."
            )

        if missing_temperature_max > 0:
            warnings.append(
                f"{missing_temperature_max} rows have no "
                "maximum temperature measurement."
            )

        if missing_humidity == len(working):
            warnings.append(
                "Humidity is unavailable in the current "
                "historical source datasets. This is expected."
            )
        elif missing_humidity > 0:
            warnings.append(
                f"{missing_humidity} rows have no humidity "
                "measurement."
            )



        # Monthly rainfall cannot be negative.
        invalid_rainfall_mask = (
            working["rainfall_mm"].notna()
            & (
                working["rainfall_mm"] < 0
            )
        )

        invalid_rainfall = int(
            invalid_rainfall_mask.sum()
        )

        if invalid_rainfall > 0:
            errors.append(
                f"{invalid_rainfall} negative rainfall "
                "values detected."
            )


        invalid_temperature_min_mask = (
            working[
                "temperature_min_c"
            ].notna()
            & (
                (
                    working[
                        "temperature_min_c"
                    ] < -10
                )
                |
                (
                    working[
                        "temperature_min_c"
                    ] > 50
                )
            )
        )

        invalid_temperature_max_mask = (
            working[
                "temperature_max_c"
            ].notna()
            & (
                (
                    working[
                        "temperature_max_c"
                    ] < -10
                )
                |
                (
                    working[
                        "temperature_max_c"
                    ] > 55
                )
            )
        )

        invalid_temperature_min = int(
            invalid_temperature_min_mask.sum()
        )

        invalid_temperature_max = int(
            invalid_temperature_max_mask.sum()
        )

        if invalid_temperature_min > 0:
            errors.append(
                f"{invalid_temperature_min} suspicious "
                "minimum temperature values detected."
            )

        if invalid_temperature_max > 0:
            errors.append(
                f"{invalid_temperature_max} suspicious "
                "maximum temperature values detected."
            )

    
        invalid_relationship_mask = (
            working[
                "temperature_min_c"
            ].notna()
            & working[
                "temperature_max_c"
            ].notna()
            & (
                working[
                    "temperature_min_c"
                ]
                >
                working[
                    "temperature_max_c"
                ]
            )
        )

        invalid_temperature_relationship = int(
            invalid_relationship_mask.sum()
        )

        if invalid_temperature_relationship > 0:
            errors.append(
                f"{invalid_temperature_relationship} rows "
                "have Tmin > Tmax."
            )

        invalid_latitude_mask = (
            working["latitude"].notna()
            & (
                (working["latitude"] < -90)
                | (working["latitude"] > 90)
            )
        )

        invalid_longitude_mask = (
            working["longitude"].notna()
            & (
                (working["longitude"] < -180)
                | (working["longitude"] > 180)
            )
        )

        invalid_latitude = int(
            invalid_latitude_mask.sum()
        )

        invalid_longitude = int(
            invalid_longitude_mask.sum()
        )

        if invalid_latitude > 0:
            errors.append(
                f"{invalid_latitude} invalid latitude "
                "values detected."
            )

        if invalid_longitude > 0:
            errors.append(
                f"{invalid_longitude} invalid longitude "
                "values detected."
            )


        total_stations = int(
            working[
                "station_id"
            ].dropna().nunique()
        )

        return WeatherValidationResult(
            is_valid=len(errors) == 0,

            total_rows=len(working),
            total_stations=total_stations,

            empty_rows=empty_rows,
            missing_identity_rows=missing_identity_rows,
            rows_without_measurement=rows_without_measurement,

            duplicate_rows=duplicate_rows,
            duplicate_groups=duplicate_groups,

            missing_rainfall=missing_rainfall,
            missing_temperature_min=missing_temperature_min,
            missing_temperature_max=missing_temperature_max,
            missing_humidity=missing_humidity,

            invalid_rainfall=invalid_rainfall,
            invalid_temperature_min=invalid_temperature_min,
            invalid_temperature_max=invalid_temperature_max,

            invalid_temperature_relationship=(
                invalid_temperature_relationship
            ),

            invalid_latitude=invalid_latitude,
            invalid_longitude=invalid_longitude,

            warnings=warnings,
            errors=errors,
        )
