from pathlib import Path
from datetime import datetime, timezone, date

import pandas as pd

from app.weather_model.context.schemas import (
    ClimatologyResult,
    ClimatologyValue,
)

class ClimatologyProvider:

    TARGETS = {
        "rainfall_mm": ("rainfall", "mm/month"),
        "temperature_min_c": ("temperature_min", "°C"),
        "temperature_max_c": ("temperature_max", "°C"),
    }

    def __init__(
        self,
        data_root: str | Path = "data/weather/modeling/prophet",
        min_years: int = 3,
        history_cutoff: date | None = None,
    ):
        self.data_root = Path(data_root)

        if min_years < 1:
            raise ValueError("min_years must be positive")

        self.min_years = min_years
        self.history_cutoff = history_cutoff

    def get_climatology(
        self,
        district_id: int,
        travel_date: date,
    ) -> ClimatologyResult:

        if district_id <= 0:
            raise ValueError("district_id must be positive")

        requested_month = travel_date.replace(day=1)

        values = {}
        missing = []

        for target, (field_name, unit) in self.TARGETS.items():

            value = self._calculate_target(
                district_id=district_id,
                target=target,
                month=travel_date.month,
                unit=unit,
            )

            values[field_name] = value

            if value is None:
                missing.append(target)

        available = any(
            value is not None
            for value in values.values()
        )

        if not available:
            message = (
                "Insufficient historical monthly observations "
                "for the requested district and calendar month."
            )
        elif missing:
            message = (
                "Partial historical monthly climatology is available. "
                "Some weather targets have insufficient observations."
            )
        else:
            message = (
                "Historical monthly climatology calculated from "
                "available district observations. These values "
                "are not daily weather forecasts."
            )

        return ClimatologyResult(
            district_id=district_id,
            requested_month=requested_month,
            available=available,
            rainfall=values["rainfall"],
            temperature_min=values["temperature_min"],
            temperature_max=values["temperature_max"],
            missing_targets=missing,
            message=message,
        )

    def _calculate_target(
        self,
        district_id: int,
        target: str,
        month: int,
        unit: str,
    ) -> ClimatologyValue | None:

        file_path = (
            self.data_root
            / target
            / f"district_{district_id}_full.csv"
        )

        if not file_path.is_file():
            return None

        df = pd.read_csv(file_path)

        if not {"ds", "y"}.issubset(df.columns):
            raise ValueError(
                f"Invalid weather modeling file: {file_path}"
            )

        df["ds"] = pd.to_datetime(
            df["ds"],
            errors="coerce",
        )

        df["y"] = pd.to_numeric(
            df["y"],
            errors="coerce",
        )

        df = df.dropna(subset=["ds", "y"]).copy()

        # The source dataset is monthly, not daily.
        df["month_start"] = (
            df["ds"].dt.to_period("M").dt.to_timestamp()
        )

        # Avoid accidentally including future observations.
        if self.history_cutoff is not None:
            cutoff = pd.Timestamp(
                self.history_cutoff
            ).to_period("M").to_timestamp()

            df = df[df["month_start"] <= cutoff]

        # Reject duplicate month records rather than
        # allowing them to distort climatological averages.
        if df["month_start"].duplicated().any():
            raise ValueError(
                f"Duplicate district-month records in {file_path}"
            )

        df = df[
            df["month_start"].dt.month == month
        ].copy()

        if df.empty:
            return None

        years = sorted(
            df["month_start"].dt.year.unique().tolist()
        )

        if len(years) < self.min_years:
            return None

        series = df["y"]

        return ClimatologyValue(
            target=target,
            mean=round(float(series.mean()), 3),
            minimum=round(float(series.min()), 3),
            maximum=round(float(series.max()), 3),
            standard_deviation=(
                round(float(series.std(ddof=1)), 3)
                if len(series) > 1
                else None
            ),
            unit=unit,
            observation_years=len(years),
            first_year=int(years[0]),
            last_year=int(years[-1]),
        )