"""Attraction Seasonality Lookup Service (Stage 12.4C Task K).

Provides read-only access to monthly climate profiles and explainable seasonality features
for any attraction by resolving to its parent district or specific attraction sample.
Does not alter ranking scores or mix separate attraction samples into district climatology.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.models.district import District
from app.models.climate import (
    ClimateAttractionMapping,
    ClimateDatasetVersion,
    ClimateDistrictMonthlyClimatology,
    ClimateSeasonalityFeature,
)


class AttractionSeasonalityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_attraction_monthly_climate(
        self,
        attraction_id: int,
        month: int,
        dataset_version_name: str = "nasa_power_daily_v2.10.0_historical_2010_2025_batch02",
        feature_version: str = "12.4c_v1",
    ) -> dict[str, Any]:
        """Look up monthly climate information and seasonality features for an attraction.

        Resolves parent district, retrieves 16-year climatology and explainable features.
        If the attraction has a dedicated coordinate sample (Batch 01), flags its availability
        without polluting district climatology.
        """
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month: {month}. Must be between 1 and 12.")

        # 1. Fetch attraction and district
        attr_stmt = (
            select(Attraction, District)
            .join(District, Attraction.district_id == District.id)
            .where(Attraction.id == attraction_id)
        )
        attr_res = await self.session.execute(attr_stmt)
        row = attr_res.first()
        if not row:
            raise ValueError(f"Attraction with ID {attraction_id} not found.")

        attraction, district = row

        # 2. Check if dedicated attraction sample exists (e.g. Batch 01, dataset version 2)
        dedicated_stmt = (
            select(ClimateAttractionMapping)
            .join(ClimateDatasetVersion, ClimateAttractionMapping.dataset_version_id == ClimateDatasetVersion.id)
            .where(
                ClimateAttractionMapping.attraction_id == attraction_id,
                ClimateDatasetVersion.product_version == "nasa_power_daily_v2.10.0_historical_2010_2025_batch01",
            )
        )
        dedicated_res = await self.session.execute(dedicated_stmt)
        has_dedicated_sample = dedicated_res.scalar_one_or_none() is not None

        # 3. Retrieve authoritative district climatology for requested month
        clim_stmt = (
            select(ClimateDistrictMonthlyClimatology)
            .join(ClimateDatasetVersion, ClimateDistrictMonthlyClimatology.dataset_version_id == ClimateDatasetVersion.id)
            .where(
                ClimateDistrictMonthlyClimatology.district_id == district.id,
                ClimateDistrictMonthlyClimatology.month == month,
                ClimateDatasetVersion.product_version == dataset_version_name,
            )
        )
        clim_res = await self.session.execute(clim_stmt)
        climatology = clim_res.scalar_one_or_none()

        # 4. Retrieve seasonality features for requested month
        feat_stmt = (
            select(ClimateSeasonalityFeature)
            .join(ClimateDatasetVersion, ClimateSeasonalityFeature.dataset_version_id == ClimateDatasetVersion.id)
            .where(
                ClimateSeasonalityFeature.district_id == district.id,
                ClimateSeasonalityFeature.month == month,
                ClimateSeasonalityFeature.feature_version == feature_version,
                ClimateDatasetVersion.product_version == dataset_version_name,
            )
        )
        feat_res = await self.session.execute(feat_stmt)
        features = feat_res.scalar_one_or_none()

        return {
            "attraction": {
                "id": attraction.id,
                "name": attraction.name,
                "latitude": float(attraction.latitude) if attraction.latitude else None,
                "longitude": float(attraction.longitude) if attraction.longitude else None,
                "district_id": district.id,
                "district_name": district.name,
            },
            "query_month": month,
            "resolution_mode": "DISTRICT_REPRESENTATIVE_FALLBACK",
            "has_dedicated_attraction_sample": has_dedicated_sample,
            "dedicated_sample_note": (
                "A dedicated attraction-coordinate historical series is archived under Batch 01 (dataset_version_id=2). "
                "District climatology is kept strictly unpolluted."
                if has_dedicated_sample
                else "No attraction-specific historical coordinate series; using district representative."
            ),
            "climatology": {
                "rainfall_mean_mm": climatology.rainfall_mean_mm if climatology else None,
                "rainfall_median_mm": climatology.rainfall_median_mm if climatology else None,
                "rainfall_std_mm": climatology.rainfall_std_mm if climatology else None,
                "rainfall_cv": climatology.rainfall_cv if climatology else None,
                "temp_mean_c": climatology.temp_mean_c if climatology else None,
                "temp_max_mean_c": climatology.temp_max_mean_c if climatology else None,
                "temp_min_mean_c": climatology.temp_min_mean_c if climatology else None,
                "relative_humidity_mean_pct": climatology.relative_humidity_mean_pct if climatology else None,
                "solar_radiation_mean_mj": climatology.solar_radiation_mean_mj if climatology else None,
                "rainy_day_frequency_mean": climatology.rainy_day_frequency_mean if climatology else None,
                "reference_period": climatology.reference_period if climatology else None,
                "valid_years_count": climatology.valid_years_count if climatology else None,
            } if climatology else None,
            "seasonality_features": {
                "relative_rainfall_favorability": features.relative_rainfall_favorability if features else None,
                "temperature_comfort_index": features.temperature_comfort_index if features else None,
                "humidity_comfort_index": features.humidity_comfort_index if features else None,
                "rainfall_reliability_index": features.rainfall_reliability_index if features else None,
                "seasonality_uncertainty_score": features.seasonality_uncertainty_score if features else None,
                "baseline_a_rainfall_rank": features.baseline_a_rainfall_rank if features else None,
                "baseline_b_multivar_score": features.baseline_b_multivar_score if features else None,
                "baseline_b_multivar_rank": features.baseline_b_multivar_rank if features else None,
                "baseline_c_variability_rank": features.baseline_c_variability_rank if features else None,
                "feature_version": features.feature_version if features else None,
            } if features else None,
            "source_provenance": {
                "dataset_version": dataset_version_name,
                "geographic_uncertainty": "DISTRICT_REPRESENTATIVE_POINT",
                "disclaimer": "Derived from 0.5x0.5 deg NASA POWER model/reanalysis data. Represents district-level macroclimate and may not reflect microclimatic elevation or local coastal gradients.",
            },
        }
