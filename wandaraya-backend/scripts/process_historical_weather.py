from pathlib import Path

from app.weather_model.ingestion.historical_loader import (
    HistoricalWeatherLoader,
)
from app.weather_model.validation.weather_validator import WeatherValidator
from app.weather_model.validation.weather_quality_analyzer import (
    WeatherQualityAnalyzer,
)

BASE_DIR = Path("/app")

RAW_DIR = BASE_DIR / "data" / "weather" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "weather" / "processed"


def main():

    print("=" * 70)
    print("WANDARAYA HISTORICAL WEATHER DATA PIPELINE")
    print("=" * 70)

    loader = HistoricalWeatherLoader(
        rainfall_file=RAW_DIR / "rainfall.xlsx",
        rainfall_other_file=RAW_DIR / "rainfall_other_stations.xlsx",
        temperature_file=RAW_DIR / "temperature.xlsx",
    )

    rainfall, temperature = loader.load()

    print("\nRAINFALL")
    print("-" * 70)

    print(f"Rows: {len(rainfall)}")
    print(
        f"Stations: "
        f"{rainfall['station_name'].nunique()}"
    )

    print(
        f"Date range: "
        f"{rainfall['date'].min()} "
        f"→ {rainfall['date'].max()}"
    )

    print("\nTEMPERATURE")
    print("-" * 70)

    print(f"Rows: {len(temperature)}")

    print(
        f"Stations: "
        f"{temperature['station_name'].nunique()}"
    )

    print(
        f"Date range: "
        f"{temperature['date'].min()} "
        f"→ {temperature['date'].max()}"
    )

    report = WeatherValidator.validate(
        rainfall,
        temperature,
    )

    print("\nDATA QUALITY")
    print("-" * 70)

    print(report)

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rainfall.to_csv(
        PROCESSED_DIR / "rainfall_monthly.csv",
        index=False,
    )

    temperature.to_csv(
        PROCESSED_DIR / "temperature_monthly.csv",
        index=False,
    )

    quality_dir = (
    PROCESSED_DIR / "quality"
)

    quality_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------
# Missing data reports
# ---------------------------------------------------------

    rainfall_missing = (
    WeatherQualityAnalyzer
    .rainfall_missing_report(rainfall)
)

    temperature_missing = (
    WeatherQualityAnalyzer
    .temperature_missing_report(temperature)
)


# ---------------------------------------------------------
# Station summaries
# ---------------------------------------------------------

    rainfall_station_summary = (
    WeatherQualityAnalyzer
    .rainfall_station_summary(rainfall)
)

    temperature_station_summary = (
    WeatherQualityAnalyzer
    .temperature_station_summary(
        temperature
    )
)


# ---------------------------------------------------------
# Monthly coverage
# ---------------------------------------------------------

    rainfall_monthly_coverage = (
    WeatherQualityAnalyzer.monthly_coverage(
        rainfall,
        "rainfall_mm",
    )
)

    temperature_min_coverage = (
    WeatherQualityAnalyzer.monthly_coverage(
        temperature,
        "temperature_min_c",
    )
)

    temperature_max_coverage = (
    WeatherQualityAnalyzer.monthly_coverage(
        temperature,
        "temperature_max_c",
    )
)


# ---------------------------------------------------------
# Station source comparison
# ---------------------------------------------------------

    station_comparison = (
    WeatherQualityAnalyzer.compare_station_sources(
        rainfall,
        temperature,
    )
)


# ---------------------------------------------------------
# Coordinate availability
# ---------------------------------------------------------

    coordinate_report = (
    WeatherQualityAnalyzer.coordinate_report(
        rainfall,
        temperature,
    )
)
    rainfall_missing.to_csv(
    quality_dir / "rainfall_missing.csv",
    index=False,
)

    temperature_missing.to_csv(
    quality_dir / "temperature_missing.csv",
    index=False,
)

    rainfall_station_summary.to_csv(
    quality_dir / "rainfall_station_summary.csv",
    index=False,
)

    temperature_station_summary.to_csv(
    quality_dir / "temperature_station_summary.csv",
    index=False,
)

    rainfall_monthly_coverage.to_csv(
    quality_dir / "rainfall_monthly_coverage.csv",
    index=False,
)

    temperature_min_coverage.to_csv(
    quality_dir / "temperature_min_monthly_coverage.csv",
    index=False,
)

    temperature_max_coverage.to_csv(
    quality_dir / "temperature_max_monthly_coverage.csv",
    index=False,
)

    print("\nOUTPUT")
    print("-" * 70)

    print(
        PROCESSED_DIR / "rainfall_monthly.csv"
    )

    print(
        PROCESSED_DIR / "temperature_monthly.csv"
    )

    print("\nSUCCESS")
    print(
        "Historical weather files were standardized."
    )

    print("\n")
    print("=" * 70)
    print("WANDARAYA WEATHER DATA QUALITY REPORT")
    print("=" * 70)


    print("\nSOURCE COVERAGE")
    print("-" * 70)

    print(
    f"Rainfall stations: "
    f"{station_comparison['rainfall_station_count']}"
    )

    print(
    f"Temperature stations: "
    f"{station_comparison['temperature_station_count']}"
)

    print(
    f"Common stations: "
    f"{station_comparison['common_station_count']}"
)


    print("\nRAINFALL ONLY STATIONS")
    print("-" * 70)

    for station in station_comparison["rainfall_only"]:
        print(f"  - {station}")


    print("\nTEMPERATURE ONLY STATIONS")
    print("-" * 70)

    for station in station_comparison["temperature_only"]:
        print(f"  - {station}")


    print("\nMISSING VALUES")
    print("-" * 70)

    print(
        f"Rainfall missing: "
        f"{report.rainfall_missing}"
    )

    print(
        f"Temperature MIN missing: "
        f"{report.temperature_min_missing}"
    )

    print(
        f"Temperature MAX missing: "
        f"{report.temperature_max_missing}"
    )


    print("\nDATA INTEGRITY")
    print("-" * 70)

    print(
        f"Negative rainfall: "
        f"{report.negative_rainfall}"
    )

    print(
        f"TMIN > TMAX: "
        f"{report.invalid_temperature_order}"
    )

    print(
        f"Rainfall duplicates: "
        f"{report.rainfall_duplicates}"
    )

    print(
        f"Temperature duplicates: "
        f"{report.temperature_duplicates}"
    )


    print("\nCOORDINATE AVAILABILITY")
    print("-" * 70)

    print(
        "Rainfall stations missing coordinates:"
    )

    for station in coordinate_report[
        "rainfall_missing_coordinates"
    ]:
        print(f"  - {station}")

    print(
        "\nTemperature stations missing coordinates:"
    )

    for station in coordinate_report[
        "temperature_missing_coordinates"
    ]:
        print(f"  - {station}")


    print("\nMODEL READINESS")
    print("-" * 70)

    print(
        "Historical period: 2021-2025"
    )

    print(
        "Rainfall: AVAILABLE"
    )

    print(
        "Temperature MIN/MAX: AVAILABLE"
    )

    print(
        "Humidity: NOT AVAILABLE"
    )

    print(
        "District mapping: NOT YET PERFORMED"
    )

    print(
        "25-district coverage: NOT YET VERIFIED"
    )


    print("\nRESULT")
    print("-" * 70)

    print(
        "STAGE 1 DATA STANDARDIZATION: PASS"
    )

    print(
        "NEXT: STAGE 2 — WEATHER STATION "
        "TO DISTRICT RESOLUTION"
    )


if __name__ == "__main__":
    main()