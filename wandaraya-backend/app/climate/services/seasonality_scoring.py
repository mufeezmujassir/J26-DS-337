"""Read-only historical-climate evidence for experimental recommendation use.

The contract intentionally returns explicit unavailable states. It never
represents historical climatology as a live forecast and never changes a
production ranking.
"""
from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.climate import (
    ClimateAttractionActivityMapping,
    ClimateAttractionActivitySeasonality,
    ClimateSeasonalityFeature,
)

MODEL_VERSION = "stage12_4f_conservative_v1"
EVIDENCE_KIND = "HISTORICAL_CLIMATE_SEASONALITY"


class FallbackStatus(StrEnum):
    FALLBACK_NOT_REQUIRED = "FALLBACK_NOT_REQUIRED"
    DISTRICT_BASELINE_FALLBACK_APPLIED = "DISTRICT_BASELINE_FALLBACK_APPLIED"
    FALLBACK_UNAVAILABLE = "FALLBACK_UNAVAILABLE"
    PROFILE_UNAVAILABLE = "PROFILE_UNAVAILABLE"
    MAPPING_UNSUPPORTED = "MAPPING_UNSUPPORTED"


class SeasonalityScoringError(Exception):
    """Base error for invalid use of the experimental scoring contract."""


class InvalidSeasonalityRequestError(SeasonalityScoringError):
    """Raised for invalid requests not already rejected by Pydantic."""


class SeasonalityScoreRequest(BaseModel):
    attraction_id: int = Field(gt=0)
    activity_type_id: int = Field(gt=0)
    travel_date: date | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    district_id: int | None = None
    mapping_evidence_tier: str | None = None
    # Compatibility-only caller assertion. Persisted evidence is authoritative.
    geographic_evidence_level: str | None = None

    @model_validator(mode="after")
    def require_time(self):
        if self.travel_date is None and self.month is None:
            raise ValueError("travel_date or month is required")
        if self.travel_date is not None and self.month is not None and self.travel_date.month != self.month:
            raise ValueError("travel_date and month disagree")
        return self


class SeasonalityScoreResult(BaseModel):
    attraction_id: int
    activity_type_id: int
    month: int
    seasonality_suitability_score: float | None = Field(default=None, ge=0, le=1)
    suitability_category: str | None = None
    availability_status: str
    fallback_status: FallbackStatus
    model_version: str = MODEL_VERSION
    experimental: bool = True
    evidence_kind: str = EVIDENCE_KIND
    is_live_weather_forecast: bool = False
    climate_feature_provenance: dict = Field(default_factory=dict)
    activity_mapping_confidence: str = "UNKNOWN"
    geographic_evidence_level: str = "UNAVAILABLE"
    district_proxy_used: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    missing_data_indicators: list[str] = Field(default_factory=list)
    explanation_metadata: dict = Field(default_factory=dict)
    evidence_limitations: list[str] = Field(default_factory=list)
    production_ranking_changed: bool = False


def category(score: float) -> str:
    if score >= .75:
        return "HIGH_RELATIVE_CLIMATE_FAVORABILITY"
    if score >= .5:
        return "MODERATE_RELATIVE_CLIMATE_FAVORABILITY"
    return "LOW_RELATIVE_CLIMATE_FAVORABILITY"


class ExperimentalSeasonalityScoringService:
    """Return evidence only; never use it as an implicit production reranker."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.last_query_count = 0

    async def score(self, request: SeasonalityScoreRequest) -> SeasonalityScoreResult:
        return (await self.score_batch([request]))[0]

    async def score_batch(self, requests: list[SeasonalityScoreRequest]) -> list[SeasonalityScoreResult]:
        if not requests:
            self.last_query_count = 0
            return []
        keys = {(r.attraction_id, r.activity_type_id) for r in requests}
        resolved = [(r.attraction_id, r.activity_type_id, r.month or r.travel_date.month) for r in requests]
        mapping_rows = (await self.db.execute(
            select(ClimateAttractionActivityMapping)
            .where(tuple_(ClimateAttractionActivityMapping.attraction_id, ClimateAttractionActivityMapping.activity_type_id).in_(keys))
            .order_by(ClimateAttractionActivityMapping.id.desc())
        )).scalars().all()
        mappings = {}
        for row in mapping_rows:
            mappings.setdefault((row.attraction_id, row.activity_type_id), row)
        profile_rows = (await self.db.execute(
            select(ClimateAttractionActivitySeasonality).where(
                tuple_(ClimateAttractionActivitySeasonality.attraction_id,
                       ClimateAttractionActivitySeasonality.activity_type_id,
                       ClimateAttractionActivitySeasonality.month).in_(resolved),
                ClimateAttractionActivitySeasonality.is_active.is_(True),
            )
        )).scalars().all()
        profiles = {(p.attraction_id, p.activity_type_id, p.month): p for p in profile_rows}
        fallback_keys = {
            (p.district_id, p.dataset_version_id, p.month)
            for p in profile_rows
            if (m := mappings.get((p.attraction_id, p.activity_type_id))) is not None
            and (not m.is_eligible_for_offline_evaluation or m.evidence_tier not in {"A", "B"})
        }
        baselines = {}
        if fallback_keys:
            rows = (await self.db.execute(select(ClimateSeasonalityFeature).where(
                tuple_(ClimateSeasonalityFeature.district_id,
                       ClimateSeasonalityFeature.dataset_version_id,
                       ClimateSeasonalityFeature.month).in_(fallback_keys),
                ClimateSeasonalityFeature.feature_version == "12.4c_v1",
            ))).scalars().all()
            baselines = {(b.district_id, b.dataset_version_id, b.month): b for b in rows}
        self.last_query_count = 2 + int(bool(fallback_keys))
        return [self._result(r, mappings.get((r.attraction_id, r.activity_type_id)), profiles.get(key), baselines)
                for r, key in zip(requests, resolved)]

    @staticmethod
    def _result(request, mapping, profile, baselines) -> SeasonalityScoreResult:
        month = request.month or request.travel_date.month
        common = dict(attraction_id=request.attraction_id, activity_type_id=request.activity_type_id, month=month)
        limitations = ["Historical seasonal suitability is not a live weather forecast.",
                       "This result is not an environmental or operational safety certification."]
        if mapping is None or not mapping.is_eligible_for_seasonality or mapping.mapping_validation_status == "UNSUPPORTED":
            return SeasonalityScoreResult(**common, availability_status="UNAVAILABLE",
                fallback_status=FallbackStatus.MAPPING_UNSUPPORTED,
                fallback_reason="No supported persisted attraction-activity mapping is available.",
                missing_data_indicators=["supported_mapping"], evidence_limitations=limitations)
        confidence = mapping.evidence_tier or mapping.confidence_level or "UNKNOWN"
        if profile is None:
            return SeasonalityScoreResult(**common, availability_status="UNAVAILABLE",
                fallback_status=FallbackStatus.PROFILE_UNAVAILABLE, activity_mapping_confidence=confidence,
                fallback_reason="No active persisted monthly seasonality profile is available.",
                missing_data_indicators=["monthly_seasonality_profile"], evidence_limitations=limitations)
        authoritative_geo = profile.climate_source_type
        mismatch = bool(request.geographic_evidence_level and request.geographic_evidence_level != authoritative_geo)
        missing = ([] if profile.feature_contributions_json else ["feature_contributions"])
        if mismatch:
            missing.append("request_geographic_evidence_mismatch_ignored")
        weak = not mapping.is_eligible_for_offline_evaluation or mapping.evidence_tier not in {"A", "B"}
        score = float(profile.climate_favorability_score)
        fallback_status = FallbackStatus.FALLBACK_NOT_REQUIRED
        fallback_reason = None
        if weak:
            baseline = baselines.get((profile.district_id, profile.dataset_version_id, month))
            if baseline is None:
                return SeasonalityScoreResult(**common, availability_status="UNAVAILABLE",
                    fallback_status=FallbackStatus.FALLBACK_UNAVAILABLE,
                    activity_mapping_confidence=confidence, geographic_evidence_level=authoritative_geo,
                    district_proxy_used=authoritative_geo == "DISTRICT_REPRESENTATIVE_PROXY",
                    fallback_reason="Weak mapping requires a district reference, but no matching persisted baseline exists; the weak profile was not used.",
                    missing_data_indicators=sorted(set(missing + ["district_multivariable_baseline"])),
                    climate_feature_provenance={"source_dataset_id": profile.dataset_version_id},
                    evidence_limitations=sorted(set(list(profile.limitations_json or []) + limitations)))
            score = float(baseline.baseline_b_multivar_score)
            fallback_status = FallbackStatus.DISTRICT_BASELINE_FALLBACK_APPLIED
            fallback_reason = "Weak or offline-ineligible mapping; persisted district multivariable historical-climate fallback used."
        explanation = profile.explanation_json or {}
        return SeasonalityScoreResult(**common, availability_status="AVAILABLE",
            seasonality_suitability_score=score, suitability_category=category(score),
            fallback_status=fallback_status,
            fallback_used=fallback_status == FallbackStatus.DISTRICT_BASELINE_FALLBACK_APPLIED,
            fallback_reason=fallback_reason, activity_mapping_confidence=confidence,
            geographic_evidence_level=authoritative_geo,
            district_proxy_used=authoritative_geo == "DISTRICT_REPRESENTATIVE_PROXY",
            climate_feature_provenance={"source_dataset_id": profile.dataset_version_id,
                "historical_reference_period": explanation.get("historical_reference_period"),
                "climate_source": explanation.get("climate_source"),
                "authoritative_climate_source_type": authoritative_geo,
                "feature_contributions": profile.feature_contributions_json,
                "request_geographic_evidence_assertion": request.geographic_evidence_level,
                "request_assertion_matched": None if request.geographic_evidence_level is None else not mismatch},
            missing_data_indicators=missing,
            explanation_metadata={"summary": explanation.get("summary"),
                "relative_monthly_rank": profile.climate_favorability_rank,
                "evidence_status": profile.evidence_status},
            evidence_limitations=sorted(set(list(profile.limitations_json or []) + limitations)))
