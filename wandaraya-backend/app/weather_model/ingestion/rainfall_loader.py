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


class RainfallLoader:

    @staticmethod
    def load_main_file(file_path: str | Path) -> pd.DataFrame:

        df = pd.read_excel(file_path)

        # Normalize column names because rf.xlsx contains "Jan "
        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        # Remove empty/footer rows such as "Values in mm"
        df = df[
            pd.to_numeric(df["yyyy"], errors="coerce").notna()
        ].copy()

        df["yyyy"] = df["yyyy"].astype(int)

        month_columns = [
            month
            for month in MONTH_MAP
            if month in df.columns
        ]

        melted = df.melt(
            id_vars=[
                "id",
                "station_name",
                "longitude",
                "latitude",
                "yyyy",
            ],
            value_vars=month_columns,
            var_name="month_name",
            value_name="rainfall_mm",
        )

        melted["month"] = melted["month_name"].map(MONTH_MAP)

        melted["date"] = pd.to_datetime(
            dict(
                year=melted["yyyy"],
                month=melted["month"],
                day=1,
            )
        )

        melted["source_file"] = "rf.xlsx"

        return melted[
            [
                "id",
                "station_name",
                "longitude",
                "latitude",
                "date",
                "yyyy",
                "month",
                "rainfall_mm",
                "source_file",
            ]
        ]

    @staticmethod
    def load_other_stations(
        file_path: str | Path,
    ) -> pd.DataFrame:

        df = pd.read_excel(file_path)

        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        df = df.rename(
            columns={
                "Station_ID": "id",
                "station": "station_name",
                "Year": "yyyy",
                "Month": "month",
                "Total(mm)": "rainfall_mm",
            }
        )

        df = df[
            pd.to_numeric(df["yyyy"], errors="coerce").notna()
        ].copy()

        df["yyyy"] = df["yyyy"].astype(int)
        df["month"] = df["month"].astype(int)

        df["date"] = pd.to_datetime(
            dict(
                year=df["yyyy"],
                month=df["month"],
                day=1,
            )
        )

        # This file does not provide coordinates
        df["longitude"] = None
        df["latitude"] = None

        df["source_file"] = "rf_other_stations.xlsx"

        return df[
            [
                "id",
                "station_name",
                "longitude",
                "latitude",
                "date",
                "yyyy",
                "month",
                "rainfall_mm",
                "source_file",
            ]
        ]

    @classmethod
    def load_combined(
        cls,
        main_file: str | Path,
        other_file: str | Path,
    ) -> pd.DataFrame:

        main_df = cls.load_main_file(main_file)

        other_df = cls.load_other_stations(other_file)

        combined = pd.concat(
            [main_df, other_df],
            ignore_index=True,
        )

        combined["station_name"] = (
            combined["station_name"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        combined["rainfall_mm"] = pd.to_numeric(
            combined["rainfall_mm"],
            errors="coerce",
        )

        return combined.sort_values(
            ["station_name", "date"]
        ).reset_index(drop=True)