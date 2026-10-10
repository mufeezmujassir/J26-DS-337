"""Create calendar-complete Prophet input files from district-month weather data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.weather_model.validation.monthly_quality import (
    MONTHLY_TARGET_COLUMNS,
    validate_district_monthly_weather,
)


@dataclass(frozen=True)
class ProphetDatasetBuilder:
    """Build one ``ds,y`` CSV per district and target, including missing months."""

    output_dir: Path
    study_start: str = "2021-01-01"
    study_end: str = "2025-10-01"
    train_end: str = "2025-01-01"
    minimum_train_observations: int = 36
    minimum_test_observations: int = 6
    minimum_distinct_years: int = 4
    minimum_common_coverage_pct: float = 70.0

    def build(self, district_weather: pd.DataFrame) -> pd.DataFrame:
        weather = validate_district_monthly_weather(district_weather)
        study_months = pd.date_range(self.study_start, self.study_end, freq="MS")
        cutoff = pd.Timestamp(self.train_end)
        readiness_rows: list[dict[str, object]] = []

        for district_id, district_rows in weather.groupby("district_id", sort=True):
            district_name = self._district_name(district_rows)
            for target in MONTHLY_TARGET_COLUMNS:
                prophet_frame = self._calendar_complete_frame(
                    district_rows, target, study_months
                )
                self._write_splits(district_id, target, prophet_frame, cutoff)

                common = prophet_frame[prophet_frame["y"].notna()].copy()
                train = common[common["ds"] < cutoff]
                test = common[common["ds"] >= cutoff]
                common_coverage = round(len(common) / len(study_months) * 100, 2)
                distinct_years = int(common["ds"].dt.year.nunique())
                ready = (
                    len(train) >= self.minimum_train_observations
                    and len(test) >= self.minimum_test_observations
                    and distinct_years >= self.minimum_distinct_years
                    and common_coverage >= self.minimum_common_coverage_pct
                )
                readiness_rows.append(
                    {
                        "district_id": self._district_file_id(district_id),
                        "district_name": district_name,
                        "target": target,
                        "study_start": study_months.min().date().isoformat(),
                        "study_end": study_months.max().date().isoformat(),
                        "common_expected_months": len(study_months),
                        "common_observed_months": len(common),
                        "common_coverage_pct": common_coverage,
                        "train_observations": len(train),
                        "test_observations": len(test),
                        "distinct_years": distinct_years,
                        "has_duplicate_district_months": False,
                        "model_ready": ready,
                    }
                )

        return pd.DataFrame(readiness_rows).sort_values(
            ["district_id", "target"]
        ).reset_index(drop=True)

    def _calendar_complete_frame(
        self,
        district_rows: pd.DataFrame,
        target: str,
        study_months: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        observations = district_rows.loc[
            district_rows["observation_date"].isin(study_months),
            ["observation_date", target],
        ].rename(columns={"observation_date": "ds", target: "y"})
        calendar = pd.DataFrame({"ds": study_months})
        return calendar.merge(observations, on="ds", how="left")

    def _write_splits(
        self,
        district_id: object,
        target: str,
        prophet_frame: pd.DataFrame,
        cutoff: pd.Timestamp,
    ) -> None:
        folder = self.output_dir / target
        folder.mkdir(parents=True, exist_ok=True)
        prefix = f"district_{self._district_file_id(district_id)}"
        splits = {
            "full": prophet_frame,
            "train": prophet_frame[prophet_frame["ds"] < cutoff],
            "test": prophet_frame[prophet_frame["ds"] >= cutoff],
        }
        for split, frame in splits.items():
            frame.to_csv(folder / f"{prefix}_{split}.csv", index=False)

    @staticmethod
    def _district_name(rows: pd.DataFrame) -> str | None:
        if "district_name" not in rows.columns:
            return None
        names = rows["district_name"].dropna()
        return str(names.iloc[0]) if not names.empty else None

    @staticmethod
    def _district_file_id(value: object) -> str:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.notna(numeric) and float(numeric).is_integer():
            return str(int(numeric))
        return str(value)
