import pandas as pd

from app.weather_model.ingestion.validator import WeatherDataValidator

DATASET = (
    "data/weather/processed/"
    "weather_monthly_normalized.csv"
)

def main() -> None:
    df = pd.read_csv(
        DATASET, 
        parse_dates=[
            "observation_date"
        ],
    )

    validator = WeatherDataValidator()

    result = validator.validate(
        df
    )

    print()
    print("=" * 70)
    print(
        "WANDARAYA WEATHER DATA VALIDATION"
    )
    print("=" * 70)

    print(
        f"Total rows: "
        f"{result.total_rows}"
    )

    print(
        f"Stations: "
        f"{result.total_stations}"
    )

    print(
        f"Date range: "
        f"{df['observation_date'].min()} "
        f"to "
        f"{df['observation_date'].max()}"
    )

    print()

    print(
        f"Duplicate rows: "
        f"{result.duplicate_rows}"
    )

    print(
        f"Empty rows: {result.empty_rows}"
    )

    print(
        "Rows without measurements: "
        f"{result.rows_without_measurement}"
    )

    print(
        f"Missing rainfall: "
        f"{result.missing_rainfall}"
    )

    print(
        "Missing minimum temperature: "
        f"{result.missing_temperature_min}"
    )

    print(
        "Missing maximum temperature: "
        f"{result.missing_temperature_max}"
    )

    print(
        f"Invalid rainfall: "
        f"{result.invalid_rainfall}"
    )

    print(
        "Invalid minimum temperature: "
        f"{result.invalid_temperature_min}"
    )

    print(
        "Invalid maximum temperature: "
        f"{result.invalid_temperature_max}"
    )

    print(
        "Invalid temperature relationships: "
        f"{result.invalid_temperature_relationship}"
    )

    print()

    print("ERRORS")

    for error in result.errors:
        print(
            f"  - {error}"
        )

    print()

    print("WARNINGS")

    for warning in result.warnings:
        print(
            f"  - {warning}"
        )

    print()

    if result.is_valid:

        print(
            "RESULT: PASS"
        )

    else:

        print(
            "RESULT: DATA QUALITY ISSUES FOUND"
        )


if __name__ == "__main__":
    main()
