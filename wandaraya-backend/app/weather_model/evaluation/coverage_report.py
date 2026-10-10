from __future__ import annotations

import pandas as pd

from app.weather_model.validation.monthly_quality import (
    MONTHLY_TARGET_COLUMNS,
    validate_district_monthly_weather,
)


class WeatherCoverageReporter:

    def station_coverage(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        coverage = (
            df
            .groupby(
                [
                    "station_id",
                    "station_name",
                ],
                dropna=False,
            )
            .agg(
                start_date=(
                    "observation_date",
                    "min",
                ),
                end_date=(
                    "observation_date",
                    "max",
                ),
                months=(
                    "observation_date",
                    "nunique",
                ),
                rainfall_count=(
                    "rainfall_mm",
                    "count",
                ),
                temp_min_count=(
                    "temperature_min_c",
                    "count",
                ),
                temp_max_count=(
                    "temperature_max_c",
                    "count",
                ),
            )
            .reset_index()
        )

        return coverage


    def district_coverage(
        self,
        df: pd.DataFrame,
        *,
        study_start: str = "2021-01-01",
        study_end: str = "2025-10-01",
    ) -> pd.DataFrame:
        """Measure target coverage from one district row per calendar month.

        ``df`` must be the district aggregation, never the station observations;
        otherwise a district with several stations can incorrectly exceed 100%.
        """
        monthly = validate_district_monthly_weather(df)
        common_months = pd.date_range(study_start, study_end, freq="MS")
        rows: list[dict[str, object]] = []

        for district_id, district in monthly.groupby("district_id", sort=True):
            dates = district["observation_date"]
            start = dates.min()
            end = dates.max()
            operating_months = pd.date_range(start, end, freq="MS")
            row: dict[str, object] = {
                "district_id": district_id,
                "district_name": self._district_name(district),
                "operating_start_date": start.date().isoformat(),
                "operating_end_date": end.date().isoformat(),
                "operating_expected_months": len(operating_months),
                "common_start_date": common_months.min().date().isoformat(),
                "common_end_date": common_months.max().date().isoformat(),
                "common_expected_months": len(common_months),
            }
            for target in MONTHLY_TARGET_COLUMNS:
                operating_count = int(district[target].notna().sum())
                common_count = int(
                    district.loc[dates.isin(common_months), target].notna().sum()
                )
                prefix = target.removesuffix("_mm").removesuffix("_c")
                row[f"{prefix}_operating_observed_months"] = operating_count
                row[f"{prefix}_operating_coverage_pct"] = round(
                    operating_count / len(operating_months) * 100, 2
                )
                row[f"{prefix}_common_observed_months"] = common_count
                row[f"{prefix}_common_coverage_pct"] = round(
                    common_count / len(common_months) * 100, 2
                )
            rows.append(row)

        return pd.DataFrame(rows).sort_values("district_id").reset_index(drop=True)

    def add_coverage_percentages(
        self,
        coverage: pd.DataFrame,
    ) -> pd.DataFrame:
        result = coverage.copy()
        
        result["rainfall_coverage_pct"] = (
                result["rainfall_count"]
                / result["months"]
                * 100
            ).round(2)
        
        result["temp_min_coverage_pct"] = (
                result["temp_min_count"]
                / result["months"]
                * 100
            ).round(2)
        
        result["temp_max_coverage_pct"] = (
                result["temp_max_count"]
                / result["months"]
                * 100
            ).round(2)
        
        return result

    @staticmethod
    def _district_name(district: pd.DataFrame) -> str | None:
        if "district_name" not in district.columns:
            return None
        names = district["district_name"].dropna()
        return str(names.iloc[0]) if not names.empty else None

    
