"""Experimental, read-only Stage 12.4F seasonality scoring interface."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.climate import ClimateAttractionActivityMapping,ClimateAttractionActivitySeasonality,ClimateSeasonalityFeature

MODEL_VERSION="stage12_4f_conservative_v1"

class SeasonalityScoreRequest(BaseModel):
    attraction_id:int=Field(gt=0)
    activity_type_id:int=Field(gt=0)
    travel_date:date|None=None
    month:int|None=Field(default=None,ge=1,le=12)
    district_id:int|None=None
    mapping_evidence_tier:str|None=None
    geographic_evidence_level:str|None=None
    @model_validator(mode="after")
    def require_time(self):
        if self.travel_date is None and self.month is None:raise ValueError("travel_date or month is required")
        if self.travel_date is not None and self.month is not None and self.travel_date.month!=self.month:raise ValueError("travel_date and month disagree")
        return self

class SeasonalityScoreResult(BaseModel):
    attraction_id:int;activity_type_id:int;month:int
    seasonality_suitability_score:float=Field(ge=0,le=1)
    suitability_category:str;model_version:str=MODEL_VERSION;experimental:bool=True
    climate_feature_provenance:dict
    activity_mapping_confidence:str;geographic_evidence_level:str
    district_proxy_used:bool;fallback_used:bool;fallback_reason:str|None=None
    missing_data_indicators:list[str]=Field(default_factory=list)
    explanation_metadata:dict;evidence_limitations:list[str]
    production_ranking_changed:bool=False

def category(score:float)->str:
    if score>=.75:return "HIGH_RELATIVE_CLIMATE_FAVORABILITY"
    if score>=.5:return "MODERATE_RELATIVE_CLIMATE_FAVORABILITY"
    return "LOW_RELATIVE_CLIMATE_FAVORABILITY"

class ExperimentalSeasonalityScoringService:
    """Returns evidence only; callers must not silently use it as a production reranker."""
    def __init__(self,db:AsyncSession):self.db=db
    async def score(self,request:SeasonalityScoreRequest)->SeasonalityScoreResult:
        month=request.month or request.travel_date.month
        mapping=(await self.db.execute(select(ClimateAttractionActivityMapping).where(ClimateAttractionActivityMapping.attraction_id==request.attraction_id,ClimateAttractionActivityMapping.activity_type_id==request.activity_type_id))).scalar_one_or_none()
        if mapping is None:raise ValueError("attraction-activity mapping not found")
        profile=(await self.db.execute(select(ClimateAttractionActivitySeasonality).where(ClimateAttractionActivitySeasonality.attraction_id==request.attraction_id,ClimateAttractionActivitySeasonality.activity_type_id==request.activity_type_id,ClimateAttractionActivitySeasonality.month==month,ClimateAttractionActivitySeasonality.is_active.is_(True)))).scalar_one_or_none()
        if profile is None:raise ValueError("active monthly seasonality profile not found")
        weak=not mapping.is_eligible_for_offline_evaluation or mapping.evidence_tier not in {"A","B"}
        score=float(profile.climate_favorability_score)
        fallback_reason=None
        if weak:
            baseline=(await self.db.execute(select(ClimateSeasonalityFeature).where(ClimateSeasonalityFeature.district_id==profile.district_id,ClimateSeasonalityFeature.dataset_version_id==profile.dataset_version_id,ClimateSeasonalityFeature.month==month,ClimateSeasonalityFeature.feature_version=="12.4c_v1"))).scalar_one_or_none()
            if baseline is not None:
                score=float(baseline.baseline_b_multivar_score)
                fallback_reason="weak_or_ineligible_activity_mapping; district multivariable historical-climate fallback used"
            else:
                fallback_reason="weak_or_ineligible_activity_mapping; district fallback unavailable, stored profile retained and flagged"
        missing=[]
        if not profile.feature_contributions_json:missing.append("feature_contributions")
        proxy=profile.climate_source_type=="DISTRICT_REPRESENTATIVE_PROXY"
        limitations=list(profile.limitations_json or [])
        limitations.extend(["Historical seasonal suitability is not a live weather forecast.","This result is not an environmental or operational safety certification."])
        return SeasonalityScoreResult(attraction_id=request.attraction_id,activity_type_id=request.activity_type_id,month=month,
            seasonality_suitability_score=score,suitability_category=category(score),
            climate_feature_provenance={"historical_reference_period":profile.explanation_json.get("historical_reference_period"),"climate_source":profile.explanation_json.get("climate_source"),"feature_contributions":profile.feature_contributions_json},
            activity_mapping_confidence=mapping.evidence_tier or mapping.confidence_level or "UNKNOWN",geographic_evidence_level=request.geographic_evidence_level or profile.climate_source_type,
            district_proxy_used=proxy,fallback_used=weak,fallback_reason=fallback_reason,
            missing_data_indicators=missing,explanation_metadata={"summary":profile.explanation_json.get("summary"),"relative_monthly_rank":profile.climate_favorability_rank,"evidence_status":profile.evidence_status},evidence_limitations=sorted(set(limitations)))
