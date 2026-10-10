from pathlib import Path

import pandas as pd


MONTH_MAP = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


class TemperatureLoader:

    @staticmethod
    def load(file_path: str | Path) -> pd.DataFrame:

        df = pd.read_excel(file_path)

        # TEM file contains empty trailing columns.
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        df = df[
            pd.to_numeric(df["yyyy"], errors="coerce").notna()
        ].copy()

        df["yyyy"] = df["yyyy"].astype(int)

        month_columns = [
            month
            for month in MONTH_MAP
            if month in df.columns
        ]

        long_df = df.melt(
            id_vars=[
                "id",
                "station_name",
                "longitude",
                "latitude",
                "abbreviation",
                "yyyy",
            ],
            value_vars=month_columns,
            var_name="month_name",
            value_name="temperature_c",
        )

        long_df["month"] = (
            long_df["month_name"]
            .map(MONTH_MAP)
        )

        long_df["date"] = pd.to_datetime(
            dict(
                year=long_df["yyyy"],
                month=long_df["month"],
                day=1,
            )
        )

        long_df["temperature_c"] = pd.to_numeric(
            long_df["temperature_c"],
            errors="coerce",
        )

        pivot = long_df.pivot_table(
            index=[
                "id",
                "station_name",
                "longitude",
                "latitude",
                "date",
                "yyyy",
                "month",
            ],
            columns="abbreviation",
            values="temperature_c",
            aggfunc="mean",
        ).reset_index()

        pivot.columns.name = None

        pivot = pivot.rename(
            columns={
                "TMPMIN": "temperature_min_c",
                "TMPMAX": "temperature_max_c",
            }
        )

        pivot["temperature_avg_c"] = (
            pivot["temperature_min_c"]
            + pivot["temperature_max_c"]
        ) / 2

        pivot["station_name"] = (
            pivot["station_name"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        pivot["source_file"] = "temperature.xlsx"

        return pivot.sort_values(
            ["station_name", "date"]
        ).reset_index(drop=True)


        