from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd



WEATHER_COLUMNS = [
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

MONTH_COLUMNS = {
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


@dataclass
class NormalizationResult:
    dataframe: pd.DataFrame
    source_name: str
    input_rows: int
    output_rows: int
    empty_rows_removed: int
    invalid_rows_removed: int



def _clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """

    - remove completely empty rows
    - remove completely empty columns
    - strip column names
    - convert whitespace-only strings to NA

    IMPORTANT:
    This does NOT remove rows simply because a weather
    measurement is missing.
    """

    working = df.copy()

    # Remove Excel-generated unnamed empty columns
    working = working.loc[
        :,
        ~working.columns.astype(str).str.match(r"^Unnamed")
    ]

    # Normalize column names
    working.columns = [
        str(column).strip()
        for column in working.columns
    ]

    # Convert blank strings to NA
    object_columns = working.select_dtypes(
        include=["object"]
    ).columns

    for column in object_columns:
        working[column] = (
            working[column]
            .replace(r"^\s*$", pd.NA, regex=True)
        )

    before = len(working)

    # completely empty source rows
    working = working.dropna(how="all").copy()

    removed = before - len(working)

    # Remove columns that contain absolutely no information
    working = working.dropna(
        axis=1,
        how="all",
    )

    return working, removed


def _clean_station_id(value) -> Optional[str]:
    if pd.isna(value):
        return None

    value = str(value).strip()

    # Excel sometimes turns numeric IDs into "43421.0"
    if value.endswith(".0"):
        value = value[:-2]

    return value or None


def _clean_station_name(value) -> Optional[str]:
    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    return value.upper()


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def _build_date(
    year: pd.Series,
    month: pd.Series,
) -> pd.Series:

    return pd.to_datetime(
        {
            "year": pd.to_numeric(
                year,
                errors="coerce",
            ),
            "month": pd.to_numeric(
                month,
                errors="coerce",
            ),
            "day": 1,
        },
        errors="coerce",
    )


def _standardize_output(
    df: pd.DataFrame,
) -> pd.DataFrame:

    working = df.copy()

    # Ensure every standard column exists.
    # does not contain temperature and vice versa.
    for column in WEATHER_COLUMNS:
        if column not in working.columns:
            working[column] = pd.NA

    working = working[WEATHER_COLUMNS]

    working["station_id"] = (
        working["station_id"]
        .apply(_clean_station_id)
    )

    working["station_name"] = (
        working["station_name"]
        .apply(_clean_station_name)
    )

    for column in [
        "latitude",
        "longitude",
        "rainfall_mm",
        "temperature_min_c",
        "temperature_max_c",
        "humidity_percent",
    ]:
        working[column] = pd.to_numeric(
            working[column],
            errors="coerce",
        )

    working["observation_date"] = pd.to_datetime(
        working["observation_date"],
        errors="coerce",
    )

    return working.reset_index(drop=True)



def normalize_rainfall_long(
    df: pd.DataFrame,
    source_name: str = "rainfall",
) -> NormalizationResult:
    """
    Normalize rainfall source shaped like:

    Station_ID
    station
    Element_Code
    element
    Year
    Month
    Total(mm)

    Example:
    01GL041C | BENTOTA ESTATE | 5 | PRECIP |
    2021 | 1 | 175.8
    """

    input_rows = len(df)

    working, empty_removed = _clean_dataframe(df)

    required = {
        "Station_ID",
        "station",
        "Year",
        "Month",
        "Total(mm)",
    }

    missing = required - set(working.columns)

    if missing:
        raise ValueError(
            f"{source_name}: missing required columns: "
            f"{sorted(missing)}"
        )

    result = pd.DataFrame()

    result["station_id"] = working[
        "Station_ID"
    ].apply(_clean_station_id)

    result["station_name"] = working[
        "station"
    ].apply(_clean_station_name)

    result["latitude"] = pd.NA
    result["longitude"] = pd.NA

    result["observation_date"] = _build_date(
        working["Year"],
        working["Month"],
    )

    result["rainfall_mm"] = _numeric(
        working["Total(mm)"]
    )

    result["temperature_min_c"] = pd.NA
    result["temperature_max_c"] = pd.NA
    result["humidity_percent"] = pd.NA

    valid_identity = (
        result["station_id"].notna()
        & result["station_name"].notna()
        & result["observation_date"].notna()
    )

    # A rainfall source row without rainfall is not an
    # observation that should become a final rainfall record.
    valid_measurement = (
        result["rainfall_mm"].notna()
    )

    valid = (
        valid_identity
        & valid_measurement
    )

    invalid_removed = int(
        (~valid).sum()
    )

    result = result.loc[
        valid
    ].copy()

    result = _standardize_output(result)

    return NormalizationResult(
        dataframe=result,
        source_name=source_name,
        input_rows=input_rows,
        output_rows=len(result),
        empty_rows_removed=empty_removed,
        invalid_rows_removed=invalid_removed,
    )



def normalize_rainfall_other_station(
    df: pd.DataFrame,
    source_name: str = "rainfall_other_station",
) -> NormalizationResult:
    """
    Normalize the second rainfall workbook.

    The function first detects whether it follows the same
    long-format schema as rainfall source 1.

    If your second rainfall file has a different exact header
    layout, add that mapping here rather than changing the
    final standard weather schema.
    """

    working, empty_removed = _clean_dataframe(df)
    input_rows = len(df)

    long_format_columns = {
        "Station_ID",
        "station",
        "Year",
        "Month",
        "Total(mm)",
    }

    if long_format_columns.issubset(
        set(working.columns)
    ):
        result = normalize_rainfall_long(
            working,
            source_name=source_name,
        )

        # Preserve original structural cleanup count
        result.input_rows = input_rows
        result.empty_rows_removed += empty_removed

        return result


    lower_map = {
        str(column).strip().lower(): column
        for column in working.columns
    }

    station_id_col = (
        lower_map.get("station_id")
        or lower_map.get("id")
    )

    station_name_col = (
        lower_map.get("station")
        or lower_map.get("station_name")
    )

    year_col = (
        lower_map.get("year")
        or lower_map.get("yyyy")
    )

    longitude_col = lower_map.get(
        "longitude"
    )

    latitude_col = lower_map.get(
        "latitude"
    )

    available_months = [
        month
        for month in MONTH_COLUMNS
        if month in working.columns
    ]

    if (
        station_id_col is None
        or station_name_col is None
        or year_col is None
        or not available_months
    ):
        raise ValueError(
            f"{source_name}: unsupported rainfall schema. "
            f"Columns found: {list(working.columns)}"
        )

    id_vars = [
        station_id_col,
        station_name_col,
        year_col,
    ]

    if longitude_col:
        id_vars.append(longitude_col)

    if latitude_col:
        id_vars.append(latitude_col)

    melted = working.melt(
        id_vars=id_vars,
        value_vars=available_months,
        var_name="month_name",
        value_name="rainfall_mm",
    )

    melted["month"] = (
        melted["month_name"]
        .map(MONTH_COLUMNS)
    )

    result = pd.DataFrame()

    result["station_id"] = melted[
        station_id_col
    ].apply(_clean_station_id)

    result["station_name"] = melted[
        station_name_col
    ].apply(_clean_station_name)

    if latitude_col:
        result["latitude"] = _numeric(
            melted[latitude_col]
        )
    else:
        result["latitude"] = pd.NA

    if longitude_col:
        result["longitude"] = _numeric(
            melted[longitude_col]
        )
    else:
        result["longitude"] = pd.NA

    result["observation_date"] = _build_date(
        melted[year_col],
        melted["month"],
    )

    result["rainfall_mm"] = _numeric(
        melted["rainfall_mm"]
    )

    result["temperature_min_c"] = pd.NA
    result["temperature_max_c"] = pd.NA
    result["humidity_percent"] = pd.NA

    valid = (
        result["station_id"].notna()
        & result["station_name"].notna()
        & result["observation_date"].notna()
        & result["rainfall_mm"].notna()
    )

    invalid_removed = int(
        (~valid).sum()
    )

    result = result.loc[
        valid
    ].copy()

    result = _standardize_output(result)

    return NormalizationResult(
        dataframe=result,
        source_name=source_name,
        input_rows=input_rows,
        output_rows=len(result),
        empty_rows_removed=empty_removed,
        invalid_rows_removed=invalid_removed,
    )


def normalize_main_rainfall(
    df: pd.DataFrame,
    source_name: str = "rainfall",
) -> NormalizationResult:
    """Normalize the 14-station wide monthly rainfall workbook."""
    return normalize_rainfall_other_station(df, source_name=source_name)


def normalize_other_rainfall(
    df: pd.DataFrame,
    source_name: str = "rainfall_other_stations",
) -> NormalizationResult:
    """Normalize the long-format rainfall-only stations workbook."""
    return normalize_rainfall_long(df, source_name=source_name)



def normalize_temperature(
    df: pd.DataFrame,
    source_name: str = "temperature",
) -> NormalizationResult:
    """
    Normalize temperature workbook:

    id
    station_name
    longitude
    latitude
    code
    abbreviation
    yyyy
    Jan ... Dec

    abbreviation identifies:
        TMPMAX
        TMPMIN

    """

    input_rows = len(df)

    working, empty_removed = _clean_dataframe(df)

    required = {
        "id",
        "station_name",
        "longitude",
        "latitude",
        "abbreviation",
        "yyyy",
    }

    missing = required - set(
        working.columns
    )

    if missing:
        raise ValueError(
            f"{source_name}: missing required columns: "
            f"{sorted(missing)}"
        )

    available_months = [
        month
        for month in MONTH_COLUMNS
        if month in working.columns
    ]

    if not available_months:
        raise ValueError(
            f"{source_name}: no Jan-Dec columns found."
        )

 

    working["abbreviation"] = (
        working["abbreviation"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    working = working[
        working["abbreviation"].isin(
            ["TMPMIN", "TMPMAX"]
        )
    ].copy()

    # --------------------------------------------------------
    # WIDE → LONG
    # --------------------------------------------------------

    melted = working.melt(
        id_vars=[
            "id",
            "station_name",
            "longitude",
            "latitude",
            "abbreviation",
            "yyyy",
        ],
        value_vars=available_months,
        var_name="month_name",
        value_name="temperature_c",
    )

    melted["month"] = (
        melted["month_name"]
        .map(MONTH_COLUMNS)
    )

    melted["temperature_c"] = (
        pd.to_numeric(
            melted["temperature_c"],
            errors="coerce",
        )
    )

    # IMPORTANT:
    # Blank month cells in the Excel source are genuinely
    # unavailable observations.
    #
    # Do not turn them into rows containing only station/date.
    melted = melted[
        melted["temperature_c"].notna()
    ].copy()

    melted["station_id"] = (
        melted["id"]
        .apply(_clean_station_id)
    )

    melted["station_name"] = (
        melted["station_name"]
        .apply(_clean_station_name)
    )

    melted["observation_date"] = (
        _build_date(
            melted["yyyy"],
            melted["month"],
        )
    )

    melted["latitude"] = _numeric(
        melted["latitude"]
    )

    melted["longitude"] = _numeric(
        melted["longitude"]
    )

    # Remove only unusable identity/date rows.
    valid_identity = (
        melted["station_id"].notna()
        & melted["station_name"].notna()
        & melted["observation_date"].notna()
    )

    invalid_removed = int(
        (~valid_identity).sum()
    )

    melted = melted[
        valid_identity
    ].copy()

    pivoted = (
        melted.pivot_table(
            index=[
                "station_id",
                "station_name",
                "latitude",
                "longitude",
                "observation_date",
            ],
            columns="abbreviation",
            values="temperature_c",
            aggfunc="first",
        )
        .reset_index()
    )

    pivoted.columns.name = None

    result = pd.DataFrame()

    result["station_id"] = (
        pivoted["station_id"]
    )

    result["station_name"] = (
        pivoted["station_name"]
    )

    result["latitude"] = (
        pivoted["latitude"]
    )

    result["longitude"] = (
        pivoted["longitude"]
    )

    result["observation_date"] = (
        pivoted["observation_date"]
    )

    result["rainfall_mm"] = pd.NA

    if "TMPMIN" in pivoted.columns:
        result["temperature_min_c"] = (
            pivoted["TMPMIN"]
        )
    else:
        result["temperature_min_c"] = pd.NA

    if "TMPMAX" in pivoted.columns:
        result["temperature_max_c"] = (
            pivoted["TMPMAX"]
        )
    else:
        result["temperature_max_c"] = pd.NA

    result["humidity_percent"] = pd.NA

    # At least one temperature value must exist.
    has_temperature = (
        result["temperature_min_c"].notna()
        | result["temperature_max_c"].notna()
    )

    result = result[
        has_temperature
    ].copy()

    result = _standardize_output(result)

    return NormalizationResult(
        dataframe=result,
        source_name=source_name,
        input_rows=input_rows,
        output_rows=len(result),
        empty_rows_removed=empty_removed,
        invalid_rows_removed=invalid_removed,
    )


def combine_weather_sources(
    *frames: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine normalized weather sources.



    It simply combines valid normalized observations.
    """

    valid_frames = [
        frame.copy()
        for frame in frames
        if frame is not None
        and not frame.empty
    ]

    if not valid_frames:
        return pd.DataFrame(
            columns=WEATHER_COLUMNS
        )

    combined = pd.concat(
        valid_frames,
        ignore_index=True,
    )

    combined = _standardize_output(
        combined
    )


    combined = combined.dropna(
        subset=[
            "station_id",
            "station_name",
            "observation_date",
        ]
    ).copy()

    # Must contain at least one actual weather measurement.
    measurement_columns = [
        "rainfall_mm",
        "temperature_min_c",
        "temperature_max_c",
        "humidity_percent",
    ]

    has_measurement = (
        combined[
            measurement_columns
        ]
        .notna()
        .any(axis=1)
    )

    combined = combined[
        has_measurement
    ].copy()

    # Main rainfall and temperature use the same 14 station IDs. Their values
    # are complementary measurements for a single station/month, so coalesce
    # them instead of writing two rows with the same station/month identity.
    identity_columns = ["station_id", "observation_date"]
    conflicting_names = (
        combined.groupby(identity_columns, dropna=False)["station_name"]
        .nunique(dropna=True)
        .gt(1)
    )
    if conflicting_names.any():
        conflicts = conflicting_names[conflicting_names].index.tolist()
        raise ValueError(
            "A station ID maps to multiple names for the same month: "
            f"{conflicts[:5]}"
        )

    def first_present(values: pd.Series):
        present = values.dropna()
        return present.iloc[0] if not present.empty else pd.NA

    combined = (
        combined.groupby(identity_columns, as_index=False, dropna=False)
        .agg(
            {
                column: first_present
                for column in WEATHER_COLUMNS
                if column not in identity_columns
            }
        )
    )

    return (
        _standardize_output(combined)
        .sort_values(identity_columns)
        .reset_index(drop=True)
    )
