from __future__ import annotations

import pandas as pd


class StationWeatherBuilder:
    """Outer-join rainfall and temperature into one station-month record."""

    @staticmethod
    def build(rainfall: pd.DataFrame, temperature: pd.DataFrame) -> pd.DataFrame:
        rainfall_data = rainfall[["station_name", "date", "rainfall_mm", "source_file"]].copy()
        rainfall_data = rainfall_data.rename(columns={"source_file": "rainfall_source"})
        temperature_data = temperature[
            ["station_name", "date", "temperature_min_c", "temperature_max_c", "source_file"]
        ].copy()
        temperature_data = temperature_data.rename(columns={"source_file": "temperature_source"})

        for frame in (rainfall_data, temperature_data):
            frame["station_name"] = frame["station_name"].astype(str).str.strip().str.upper()
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")

        result = rainfall_data.merge(
            temperature_data,
            on=["station_name", "date"],
            how="outer",
            validate="one_to_one",
        )
        result["temperature_avg_c"] = (
            result["temperature_min_c"] + result["temperature_max_c"]
        ) / 2
        result["source"] = result[["rainfall_source", "temperature_source"]].apply(
            lambda row: "|".join(sorted({str(value) for value in row if pd.notna(value)})),
            axis=1,
        )
        return result.sort_values(["station_name", "date"]).reset_index(drop=True)
