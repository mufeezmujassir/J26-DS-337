"""Attraction Activity Seasonality Service (Stage 12.4D Task N).

Provides read-only query operations for attraction-activity seasonality profiles,
monthly comparisons, supported activities, and evidence-based explanations.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attraction import Attraction
from app.models.district import District
from app.models.climate import (
    ClimateActivityType,
    ClimateAttractionActivityMapping,
    ClimateAttractionActivitySeasonality,
    ClimateDistrictMonthlyClimatology,
)


class AttractionActivitySeasonalityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_supported_attraction_activities(self, attraction_id: int) -> list[dict[str, Any]]:
        """List all mapped activity types for an attraction with confidence and verification status."""
        stmt = (
            select(ClimateActivityType, ClimateAttractionActivityMapping)
            .join(
                ClimateAttractionActivityMapping,
                ClimateActivityType.id == ClimateAttractionActivityMapping.activity_type_id,
            )
            .where(ClimateAttractionActivityMapping.attraction_id == attraction_id)
            .order_by(ClimateActivityType.name)
        )
        res = await self.session.execute(stmt)
        rows = res.all()
        return [
            {
                "activity_type_id": act.id,
                "name": act.name,
                "family": act.activity_family,
                "type": act.activity_type,
                "variant": act.activity_variant,
                "mapping_source": mapping.mapping_source,
                "confidence_level": mapping.confidence_level,
                "verification_status": mapping.verification_status,
                "requires_external_evidence": act.requires_external_evidence,
            }
            for act, mapping in rows
        ]

    async def get_attraction_activity_seasonality(
        self,
        attraction_id: int,
        activity_type_id: int,
        processing_version: str = "12.4d_v1",
    ) -> list[dict[str, Any]]:
        """Retrieve all 12 monthly seasonality profiles for an attraction-activity pair."""
        stmt = (
            select(ClimateAttractionActivitySeasonality)
            .where(
                ClimateAttractionActivitySeasonality.attraction_id == attraction_id,
                ClimateAttractionActivitySeasonality.activity_type_id == activity_type_id,
                ClimateAttractionActivitySeasonality.processing_version == processing_version,
            )
            .order_by(ClimateAttractionActivitySeasonality.month)
        )
        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        return [
            {
                "month": r.month,
                "climate_favorability_score": r.climate_favorability_score,
                "climate_favorability_rank": r.climate_favorability_rank,
                "evidence_status": r.evidence_status,
                "confidence_level": r.confidence_level,
                "uncertainty_score": r.uncertainty_score,
                "climate_source_type": r.climate_source_type,
                "explanation_summary": r.explanation_json.get("summary"),
                "limitations": r.limitations_json,
            }
            for r in rows
        ]

    async def get_attraction_monthly_activity_profile(
        self,
        attraction_id: int,
        activity_type_id: int,
        month: int,
        processing_version: str = "12.4d_v1",
    ) -> dict[str, Any] | None:
        """Retrieve a single month's seasonality profile and full explanation."""
        stmt = (
            select(ClimateAttractionActivitySeasonality)
            .where(
                ClimateAttractionActivitySeasonality.attraction_id == attraction_id,
                ClimateAttractionActivitySeasonality.activity_type_id == activity_type_id,
                ClimateAttractionActivitySeasonality.month == month,
                ClimateAttractionActivitySeasonality.processing_version == processing_version,
            )
        )
        res = await self.session.execute(stmt)
        r = res.scalar_one_or_none()
        if not r:
            return None

        return {
            "attraction_id": r.attraction_id,
            "activity_type_id": r.activity_type_id,
            "month": r.month,
            "climate_favorability_score": r.climate_favorability_score,
            "climate_favorability_rank": r.climate_favorability_rank,
            "evidence_status": r.evidence_status,
            "confidence_level": r.confidence_level,
            "uncertainty_score": r.uncertainty_score,
            "climate_source_type": r.climate_source_type,
            "feature_contributions": r.feature_contributions_json,
            "explanation": r.explanation_json,
            "limitations": r.limitations_json,
        }

    async def compare_activity_months(
        self,
        attraction_id: int,
        activity_type_id: int,
        months: list[int],
        processing_version: str = "12.4d_v1",
    ) -> list[dict[str, Any]]:
        """Compare specific months side-by-side for an attraction-activity pair."""
        profiles = await self.get_attraction_activity_seasonality(
            attraction_id=attraction_id,
            activity_type_id=activity_type_id,
            processing_version=processing_version,
        )
        return [p for p in profiles if p["month"] in months]

    async def get_activity_seasonality_explanation(
        self,
        attraction_id: int,
        activity_type_id: int,
        month: int,
        processing_version: str = "12.4d_v1",
    ) -> dict[str, Any] | None:
        """Retrieve only the explainability payload for a month."""
        prof = await self.get_attraction_monthly_activity_profile(
            attraction_id=attraction_id,
            activity_type_id=activity_type_id,
            month=month,
            processing_version=processing_version,
        )
        return prof["explanation"] if prof else None
