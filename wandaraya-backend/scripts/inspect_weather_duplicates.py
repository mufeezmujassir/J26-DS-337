from __future__ import annotations
import pandas as pd

DATASET_PATH = (
    "data/weather/processed/"
    "weather_monthly_normalized.csv"
)


def main() -> None:

    df = pd.read_csv(
        DATASET_PATH,
        parse_dates=["observation_date"],
    )

    duplicate_mask = df.duplicated(
        subset=[
            "station_id",
            "observation_date",
        ],
        keep=False,
    )

    duplicates = (
        df[duplicate_mask]
        .sort_values(
            [
                "station_id",
                "observation_date",
            ]
        )
    )

    print()
    print("=" * 80)
    print("WANDARAYA WEATHER DUPLICATE INVESTIGATION")
    print("=" * 80)

    print(
        f"Duplicate rows: {len(duplicates)}"
    )

    duplicate_groups = (
        duplicates.groupby(
            [
                "station_id",
                "observation_date",
            ]
        )
        .ngroups
    )

    print(
        f"Duplicate station/month groups: "
        f"{duplicate_groups}"
    )

    print()
    print(duplicates.to_string(index=False))

    output = (
        "data/weather/processed/"
        "weather_duplicate_report.csv"
    )

    duplicates.to_csv(
        output,
        index=False,
    )

    print()
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()