from __future__ import annotations

import pandas as pd


class WeatherStationRegistryBuilder:

    @staticmethod
    def build(
        rainfall: pd.DataFrame,
        temperature: pd.DataFrame,
        station_metadata: pd.DataFrame | None = None,
    ) -> pd.DataFrame:

        rainfall_stations = (
            rainfall
            .groupby(
                "station_name",
                as_index=False,
            )
            .agg(
                rainfall_source_id=("id", "first"),
                rainfall_latitude=("latitude", "first"),
                rainfall_longitude=("longitude", "first"),
            )
        )

        rainfall_stations["has_rainfall"] = True

        temperature_stations = (
            temperature
            .groupby(
                "station_name",
                as_index=False,
            )
            .agg(
                temperature_source_id=("id", "first"),
                temperature_latitude=("latitude", "first"),
                temperature_longitude=("longitude", "first"),
            )
        )

        temperature_stations[
            "has_temperature"
        ] = True

        stations = rainfall_stations.merge(
            temperature_stations,
            on="station_name",
            how="outer",
        )

        stations["has_rainfall"] = (
            stations["has_rainfall"]
            .astype("boolean")
            .fillna(False)
            .astype(bool)
        )

        stations["has_temperature"] = (
            stations["has_temperature"]
            .astype("boolean")
            .fillna(False)
            .astype(bool)
        )

        # Prefer temperature coordinates.
        # Fall back to rainfall coordinates.
        stations["latitude"] = (
            stations["temperature_latitude"]
            .combine_first(
                stations["rainfall_latitude"]
            )
        )

        stations["longitude"] = (
            stations["temperature_longitude"]
            .combine_first(
                stations["rainfall_longitude"]
            )
        )

        if station_metadata is not None and not station_metadata.empty:
            required_metadata = {"station_name", "latitude", "longitude"}
            missing_metadata = required_metadata - set(station_metadata.columns)
            if missing_metadata:
                raise ValueError(
                    "Station metadata is missing columns: "
                    f"{sorted(missing_metadata)}"
                )
            metadata = station_metadata.copy()
            metadata["station_name"] = (
                metadata["station_name"].astype(str).str.strip().str.upper()
            )
            stations = stations.merge(
                metadata[["station_name", "latitude", "longitude"]],
                on="station_name",
                how="left",
                suffixes=("", "_metadata"),
            )
            stations["latitude"] = stations["latitude"].combine_first(
                pd.to_numeric(stations["latitude_metadata"], errors="coerce")
            )
            stations["longitude"] = stations["longitude"].combine_first(
                pd.to_numeric(stations["longitude_metadata"], errors="coerce")
            )
            stations = stations.drop(columns=["latitude_metadata", "longitude_metadata"])

        # Create our own stable WANDARAYA station ID.
        stations = stations.sort_values(
            "station_name"
        ).reset_index(drop=True)

        stations["station_id"] = [
            f"WST-{index:03d}"
            for index in range(
                1,
                len(stations) + 1,
            )
        ]

        stations["district_id"] = pd.NA

        return stations[
            [
                "station_id",
                "station_name",
                "latitude",
                "longitude",
                "district_id",
                "has_rainfall",
                "has_temperature",
            ]
        ]
