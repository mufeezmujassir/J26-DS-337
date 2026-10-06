from pathlib import Path

import pandas as pd

from app.weather_model.ingestion.normalizer import (
    combine_weather_sources,
    normalize_main_rainfall,
    normalize_other_rainfall,
    normalize_temperature,
)
from app.weather_model.ingestion.validator import WeatherDataValidator


TEMPERATURE_PATH = (
    "data/weather/raw/temperature.xlsx"
)

RAINFALL_PATH = (
    "data/weather/raw/rainfall.xlsx"
)

OTHER_RAINFALL_PATH = (
    "data/weather/raw/"
    "rainfall_other_stations.xlsx"
)

OUTPUT_PATH = (
    "data/weather/processed/"
    "weather_monthly_normalized.csv"
)


def main() -> None:
    print()
    print("=" * 70)
    print(
        "WANDARAYA WEATHER NORMALIZATION"
    )
    print("=" * 70)

    temperature_result = normalize_temperature(
        pd.read_excel(TEMPERATURE_PATH),
        source_name=TEMPERATURE_PATH,
    )
    rainfall_result = normalize_main_rainfall(
        pd.read_excel(RAINFALL_PATH),
        source_name=RAINFALL_PATH,
    )
    other_rainfall_result = normalize_other_rainfall(
        pd.read_excel(OTHER_RAINFALL_PATH),
        source_name=OTHER_RAINFALL_PATH,
    )

    df = combine_weather_sources(
        rainfall_result.dataframe,
        temperature_result.dataframe,
        other_rainfall_result.dataframe,
    )

    validation = WeatherDataValidator().validate(df)
    if not validation.is_valid:
        raise RuntimeError(
            "Normalized weather data failed validation: "
            + "; ".join(validation.errors)
        )

    Path(OUTPUT_PATH).parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print(
        f"Rows: {len(df)}"
    )

    print(
        f"Stations: "
        f"{df['station_id'].nunique()}"
    )

    print(
        f"Start: "
        f"{df['observation_date'].min()}"
    )

    print(
        f"End: "
        f"{df['observation_date'].max()}"
    )

    print(f"Main rainfall rows: {rainfall_result.output_rows}")
    print(f"Other rainfall rows: {other_rainfall_result.output_rows}")
    print(f"Temperature rows: {temperature_result.output_rows}")

    print()
    print(
        f"Saved: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
