"""
Unified Environmental Risk Assessment Engine for WANDARAYA Component 2.
======================================================================
Synthesizes NBRO historical landslide inventory data, OpenWeatherMap
meteorological forecasts, and future DMC (Disaster Management Centre)
flood warning adapter into a rigorous route-risk assessment.

Distinguishes the 5 required system statuses:
- RISK_DETECTED: Active weather alert or route corridor near documented landslide zone.
- NO_RISK_DETECTED: Data sources queried successfully, no threshold-exceeding hazards detected.
- RISK_ASSESSMENT_PARTIAL: Partial source availability or missing route segment telemetry.
- RISK_DATA_UNAVAILABLE: Neither landslide nor weather data could be obtained.
- DATA_STALE: Meteorological data is older than configured freshness limit.

Maintains strict separation between physical routing metrics (distance, time, fare)
and environmental hazard evaluations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.landslide_service import LandslideService, landslide_service, haversine_distance_m
from app.services.weather_risk_service import WeatherRiskService, weather_risk_service
from app.services.warning_service import (
    OfficialWarningService,
    warning_service,
    STATUS_ACTIVE,
    STATUS_NONE_FOUND,
    STATUS_UNKNOWN,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Section 8: DMC (Disaster Management Centre) Future Integration Architecture
# ============================================================================

class DMCWarningAdapterInterface(ABC):
    """
    Abstract contract for future Disaster Management Centre (DMC) flood warning integration.
    """

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns the integration and availability status of the DMC adapter."""
        pass

    @abstractmethod
    def fetch_active_warnings(
        self,
        route_coordinates: List[Tuple[float, float]]
    ) -> List[Dict[str, Any]]:
        """Queries active flood warnings intersecting route coordinates."""
        pass


class DMCFutureAdapter(DMCWarningAdapterInterface):
    """
    Production-grade stub for DMC integration. Explicitly reflects NOT_INTEGRATED status.
    Never fabricates live flood warnings or simulates fake API responses.
    """

    STATUS = "NOT_INTEGRATED"

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self.STATUS,
            "connected": False,
            "provider": "Disaster Management Centre (DMC) Sri Lanka",
            "reason": (
                "Disaster Management Centre (DMC) real-time flood warning feed is not currently integrated. "
                "Interface is prepared awaiting institutional CAP/REST API endpoints and basin polygon telemetry."
            ),
            "blocked_prerequisites": [
                "Official DMC Common Alerting Protocol (CAP-AU / CAP-LK) endpoint",
                "Automated river gauge telemetry feed from Sri Lanka Irrigation Department",
                "Machine-readable spatial boundary definitions for active flood warning zones",
            ],
            "schema_contract": {
                "expected_fields": [
                    "warning_id",
                    "hazard_type",
                    "severity_level",
                    "river_basin",
                    "affected_ds_divisions",
                    "geometry_wkt",
                    "effective_from_utc",
                    "expires_at_utc",
                ]
            },
        }

    def fetch_active_warnings(
        self,
        route_coordinates: List[Tuple[float, float]]
    ) -> List[Dict[str, Any]]:
        return []


# ============================================================================
# Section 5: Unified Environmental-Risk Assessment Engine
# ============================================================================

@dataclass
class EnvironmentalRiskAssessment:
    route_id: Optional[str]
    status: str  # RISK_DETECTED | NO_RISK_DETECTED | RISK_ASSESSMENT_PARTIAL | RISK_DATA_UNAVAILABLE | DATA_STALE
    environmental_risk_score: int  # 0 to 100
    risk_rating: str  # "LOW", "MODERATE", "ELEVATED", "HIGH", "UNKNOWN"
    assessed_at_utc: str
    detected_risks: List[str]
    landslide_summary: Dict[str, Any]
    weather_summary: Dict[str, Any]
    dmc_status: Dict[str, Any]
    evidence_and_limitations: str
    risk_score_breakdown: Dict[str, Any] = field(default_factory=dict)
    current_landslide_warning: Dict[str, Any] = field(default_factory=dict)
    realtime_weather_risk: Dict[str, Any] = field(default_factory=dict)
    environmental_safety_indicator: float = 100.0
    research_risk_metrics: Dict[str, Any] = field(default_factory=dict)
    model_risk_category: str = "Low model-estimated risk"
    official_warning_status: str = STATUS_UNKNOWN
    official_warnings: List[Dict[str, Any]] = field(default_factory=list)
    verified_closures: List[Dict[str, Any]] = field(default_factory=list)
    time_spent_in_elevated_risk_min: float = 0.0
    highest_risk_segment: Dict[str, Any] = field(default_factory=dict)
    route_risk_aggregation: Dict[str, Any] = field(default_factory=dict)
    data_freshness_seconds: float = 0.0
    confidence_status: str = "CONFIRMED_DATA"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "status": self.status,
            "environmental_risk_score": self.environmental_risk_score,
            "environmental_safety_indicator": self.environmental_safety_indicator,
            "risk_rating": self.risk_rating,
            "model_risk_category": self.model_risk_category,
            "official_warning_status": self.official_warning_status,
            "official_warnings": self.official_warnings,
            "verified_closures": self.verified_closures,
            "time_spent_in_elevated_risk_min": self.time_spent_in_elevated_risk_min,
            "highest_risk_segment": self.highest_risk_segment,
            "route_risk_aggregation": self.route_risk_aggregation,
            "risk_score_breakdown": self.risk_score_breakdown,
            "research_risk_metrics": self.research_risk_metrics,
            "current_landslide_warning": self.current_landslide_warning,
            "realtime_weather_risk": self.realtime_weather_risk,
            "data_freshness_seconds": self.data_freshness_seconds,
            "confidence_status": self.confidence_status,
            "assessed_at_utc": self.assessed_at_utc,
            "detected_risks": self.detected_risks,
            "landslide_assessment": self.landslide_summary,
            "weather_assessment": self.weather_summary,
            "nbro_database_status": self.landslide_summary.get("database_status", {}),
            "dmc_flood_warning_integration": self.dmc_status,
            "evidence_and_limitations": self.evidence_and_limitations,
        }


class EnvironmentalRiskService:
    @staticmethod
    def get_model_risk_category(score: float) -> str:
        """
        Maps a 0-100 environmental risk score to research model display categories:
          0-24.9:  Low model-estimated risk
          25-49.9: Moderate model-estimated risk
          50-74.9: Elevated model-estimated risk
          75-100:  High model-estimated risk
        Explicitly marked as research-model estimates, NOT official NBRO/DMC warning levels.
        """
        val = float(score)
        if val < 25.0:
            return "Low model-estimated risk"
        elif val < 50.0:
            return "Moderate model-estimated risk"
        elif val < 75.0:
            return "Elevated model-estimated risk"
        else:
            return "High model-estimated risk"

    @staticmethod
    def calculate_research_formula(
        landslide_susceptibility: float,
        r24: float,
        r72: float = 0.0,
        r7: float = 0.0,
        weather_score: float = 0.0,
        w_ls: float = 0.60,
        w_weather: float = 0.40,
        w_L: float = 0.60,
        w_R: float = 0.40,
    ) -> Dict[str, Any]:
        """
        Component 2 Research Hypothesis Risk Formula (Phase 7):
          rainfall_score (R) = 0.50 * R24 + 0.30 * R72 + 0.20 * R7
          dynamic_landslide_score = w_L * landslide_susceptibility (L) + w_R * rainfall_score (R)
          environmental_risk_score = w_ls * dynamic_landslide_score + w_weather * weather_score (W)
          environmental_safety_indicator = 100.0 - environmental_risk_score

        These weights (w_L=0.60, w_R=0.40, w_ls=0.60, w_weather=0.40) represent
        initial research parameters for comparative sensitivity analysis, not
        scientifically validated ground truth. The safety indicator represents
        an inverse relative hazard score, not an absolute statistical survival probability.
        """
        import math
        for name, val in [
            ("landslide_susceptibility", landslide_susceptibility),
            ("r24", r24),
            ("r72", r72),
            ("r7", r7),
            ("weather_score", weather_score)
        ]:
            if val is None or not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val) or val < 0.0:
                raise ValueError(f"Invalid input '{name}': must be a finite, non-negative numeric value.")

        ls_val = min(100.0, max(0.0, float(landslide_susceptibility)))
        r24_val = min(100.0, max(0.0, float(r24)))
        r72_val = min(100.0, max(0.0, float(r72)))
        r7_val = min(100.0, max(0.0, float(r7)))
        w_val = min(100.0, max(0.0, float(weather_score)))

        rainfall_score = round(0.50 * r24_val + 0.30 * r72_val + 0.20 * r7_val, 2)
        dynamic_landslide_score = round(w_L * ls_val + w_R * rainfall_score, 2)
        env_risk_score = round(w_ls * dynamic_landslide_score + w_weather * w_val, 2)
        safety_indicator = round(100.0 - env_risk_score, 2)

        return {
            "landslide_susceptibility": ls_val,
            "r24": r24_val,
            "r72": r72_val,
            "r7": r7_val,
            "rainfall_score": rainfall_score,
            "dynamic_landslide_score": dynamic_landslide_score,
            "weather_score": w_val,
            "weights": {
                "dynamic_landslide_weight": w_ls,
                "weather_weight": w_weather,
                "geological_susceptibility_weight": w_L,
                "rainfall_weight": w_R,
            },
            "environmental_risk_score": env_risk_score,
            "environmental_safety_indicator": safety_indicator,
            "model_risk_category": EnvironmentalRiskService.get_model_risk_category(env_risk_score),
            "scientific_disclaimer": "Safety indicator is an inverse hazard metric, not an absolute guarantee of route safety.",
        }

    @staticmethod
    def calculate_route_risk_aggregation(
        segments: List[Dict[str, Any]],
        weighting: str = "time",
        elevated_risk_threshold: float = 50.0,
    ) -> Dict[str, Any]:
        """
        Route-level environmental risk aggregation:
          AverageRisk = sum(segment_risk * segment_travel_time) / sum(segment_travel_time)
        Also evaluates:
        - Maximum segment risk
        - Time spent in elevated-risk segments (segment_risk >= 50.0)
        - Highest-risk segment and its transport mode
        - Detour and distance attributes
        """
        import math
        if not segments:
            return {
                "route_average_risk": 0.0,
                "environmental_safety_indicator": 100.0,
                "max_segment_risk": 0.0,
                "time_spent_in_elevated_risk_min": 0.0,
                "distance_in_elevated_risk_km": 0.0,
                "elevated_risk_time_ratio_pct": 0.0,
                "highest_risk_segment": None,
                "high_risk_segment_identifiers": [],
                "total_route_travel_time_min": 0.0,
                "total_route_distance_km": 0.0,
                "data_coverage_percentage": 0.0,
                "weighting_method": "none",
            }

        valid_segments = []
        for idx, s in enumerate(segments):
            risk = s.get("segment_risk")
            if risk is not None and isinstance(risk, (int, float)) and not isinstance(risk, bool) and math.isfinite(risk) and risk >= 0.0:
                valid_segments.append((idx, s, float(risk)))

        if not valid_segments:
            return {
                "route_average_risk": 0.0,
                "environmental_safety_indicator": 100.0,
                "max_segment_risk": 0.0,
                "time_spent_in_elevated_risk_min": 0.0,
                "distance_in_elevated_risk_km": 0.0,
                "elevated_risk_time_ratio_pct": 0.0,
                "highest_risk_segment": None,
                "high_risk_segment_identifiers": [],
                "total_route_travel_time_min": 0.0,
                "total_route_distance_km": 0.0,
                "data_coverage_percentage": 0.0,
                "weighting_method": "missing_data",
            }

        coverage_pct = round((len(valid_segments) / len(segments)) * 100.0, 1)
        max_risk = max(r for _, _, r in valid_segments)

        highest_seg_item = None
        for idx, s, r in valid_segments:
            if r == max_risk:
                highest_seg_item = {
                    "segment_id": str(s.get("segment_id", f"{s.get('from_node', 'u')}->{s.get('to_node', 'v')}")),
                    "from_node": s.get("from_node"),
                    "to_node": s.get("to_node"),
                    "mode": s.get("mode", "road"),
                    "segment_risk": round(r, 2),
                    "travel_time_min": float(s.get("travel_time_min", 0.0) or 0.0),
                    "distance_km": float(s.get("distance_km", 0.0) or 0.0),
                }
                break

        high_risk_ids = [
            str(s.get("segment_id", f"{s.get('from_node', 'u')}->{s.get('to_node', 'v')}"))
            for idx, s, r in valid_segments
            if r >= elevated_risk_threshold
        ]

        total_time = sum(float(s.get("travel_time_min", 0.0) or 0.0) for _, s, _ in valid_segments)
        total_dist = sum(float(s.get("distance_km", 0.0) or 0.0) for _, s, _ in valid_segments)

        elevated_time = sum(
            float(s.get("travel_time_min", 0.0) or 0.0)
            for _, s, r in valid_segments
            if r >= elevated_risk_threshold
        )
        elevated_dist = sum(
            float(s.get("distance_km", 0.0) or 0.0)
            for _, s, r in valid_segments
            if r >= elevated_risk_threshold
        )
        elevated_ratio = round((elevated_time / total_time * 100.0), 1) if total_time > 0 else 0.0

        if weighting == "time" and total_time > 0.0:
            weighted_sum = sum(r * float(s.get("travel_time_min", 0.0) or 0.0) for _, s, r in valid_segments)
            route_avg = round(weighted_sum / total_time, 2)
            used_method = "travel_time_weighted"
        else:
            if total_dist > 0.0:
                weighted_sum = sum(r * float(s.get("distance_km", 0.0) or 0.0) for _, s, r in valid_segments)
                route_avg = round(weighted_sum / total_dist, 2)
                used_method = "distance_weighted"
            else:
                route_avg = round(sum(r for _, _, r in valid_segments) / len(valid_segments), 2)
                used_method = "unweighted_mean"

        return {
            "route_average_risk": route_avg,
            "environmental_safety_indicator": round(100.0 - route_avg, 2),
            "max_segment_risk": round(max_risk, 2),
            "time_spent_in_elevated_risk_min": round(elevated_time, 1),
            "distance_in_elevated_risk_km": round(elevated_dist, 2),
            "elevated_risk_time_ratio_pct": elevated_ratio,
            "highest_risk_segment": highest_seg_item,
            "high_risk_segment_identifiers": high_risk_ids,
            "total_route_travel_time_min": round(total_time, 1),
            "total_route_distance_km": round(total_dist, 2),
            "data_coverage_percentage": coverage_pct,
            "weighting_method": used_method,
        }

    @staticmethod
    def compare_scoring_methods(
        landslide_susceptibility: float,
        r24: float,
        r72: float = 0.0,
        r7: float = 0.0,
        weather_score: float = 0.0,
    ) -> Dict[str, float]:
        """
        Phase 10: Compare alternative scoring formulations under identical inputs:
        - Weather-only
        - Landslide-only
        - Equal-weight combination (50/50)
        - Current implemented scoring
        - Proposed research formula
        """
        r_score = 0.50 * r24 + 0.30 * r72 + 0.20 * r7
        dyn_ls = 0.60 * landslide_susceptibility + 0.40 * r_score
        return {
            "method_a_weather_only": round(float(weather_score), 2),
            "method_b_landslide_only": round(float(landslide_susceptibility), 2),
            "method_c_equal_weight_50_50": round(0.50 * dyn_ls + 0.50 * weather_score, 2),
            "method_d_current_heuristic": round(min(100.0, 0.40 * landslide_susceptibility + 0.30 * weather_score + 0.30 * (r24 / 75.0 * 30.0 if r24 > 0 else 0)), 2),
            "method_e_proposed_research": round(0.60 * dyn_ls + 0.40 * weather_score, 2),
        }

    @staticmethod
    def conduct_sensitivity_analysis(
        dynamic_landslide_score: float,
        weather_score: float,
    ) -> Dict[str, float]:
        """
        Phase 10: Tests sensitivity across alternative combination weights:
        - 50% landslide / 50% weather
        - 60% landslide / 40% weather (standard)
        - 70% landslide / 30% weather
        """
        return {
            "weights_50_50": round(0.50 * dynamic_landslide_score + 0.50 * weather_score, 2),
            "weights_60_40_standard": round(0.60 * dynamic_landslide_score + 0.40 * weather_score, 2),
            "weights_70_30": round(0.70 * dynamic_landslide_score + 0.30 * weather_score, 2),
        }

    def __init__(
        self,
        landslide_svc: Optional[LandslideService] = None,
        weather_svc: Optional[WeatherRiskService] = None,
        dmc_adapter: Optional[DMCWarningAdapterInterface] = None,
        warning_svc: Optional[OfficialWarningService] = None,
    ) -> None:
        self.landslide_service = landslide_svc or landslide_service
        self.weather_service = weather_svc or weather_risk_service
        self.dmc_adapter = dmc_adapter or DMCFutureAdapter()
        self.warning_service = warning_svc or warning_service

    def assess_route(
        self,
        route_coordinates: List[Tuple[float, float]],
        route_id: Optional[str] = None,
        travel_date: Optional[date] = None,
        landslide_buffer_m: float = 1000.0,
        segments: Optional[List[Dict[str, Any]]] = None,
    ) -> EnvironmentalRiskAssessment:
        """
        Executes unified environmental risk assessment across landslide and weather domains.
        Compares historical landslide trigger rainfall with live meteorological forecasts
        to determine research-model trigger risk and calculate a unified 0-100 risk score.
        Queries official warning adapter separately so research estimates are never conflated
        with official NBRO or DMC warnings.
        """
        assessed_at = datetime.now(timezone.utc).isoformat()
        detected_risks: List[str] = []

        # Query official government warnings separately
        official_res = self.warning_service.check_official_landslide_warnings(route_coordinates)
        official_status = official_res.warning_status
        official_active_records = [w.to_dict() for w in official_res.active_warnings]

        if not route_coordinates:
            return EnvironmentalRiskAssessment(
                route_id=route_id,
                status="RISK_DATA_UNAVAILABLE",
                environmental_risk_score=0,
                risk_rating="UNKNOWN",
                assessed_at_utc=assessed_at,
                detected_risks=[],
                landslide_summary={"status": "RISK_DATA_UNAVAILABLE", "hazards": []},
                weather_summary={"status": "RISK_DATA_UNAVAILABLE", "weather_points": []},
                dmc_status=self.dmc_adapter.get_status(),
                evidence_and_limitations="No route coordinates provided for assessment.",
                risk_score_breakdown={"total_score": 0, "risk_rating": "UNKNOWN"},
                model_risk_category="Low model-estimated risk",
                official_warning_status=official_status,
                official_warnings=official_active_records,
                confidence_status="DATA_UNAVAILABLE",
            )

        # 1. Evaluate Landslide Risk
        ls_res = self.landslide_service.assess_route_summary(
            route_coordinates,
            buffer_meters=landslide_buffer_m,
        )
        ls_status = ls_res["status"]

        if ls_status == "RISK_DETECTED":
            h_count = ls_res["hazard_count"]
            closest_m = ls_res["closest_hazard_distance_m"]
            detected_risks.append(
                f"LANDSLIDE_HAZARD_ZONE: Corridor intersects within {closest_m:.0f}m of {h_count} "
                "recorded NBRO historical slope instability point(s)."
            )

        # 2. Evaluate Weather Risk
        w_res = self.weather_service.assess_route_weather(
            route_coordinates,
            travel_date=travel_date,
        )
        w_status = w_res["status"]

        if w_status == "RISK_DETECTED":
            risk_level = w_res.get("overall_risk_level", "MODERATE")
            max_p = w_res.get("max_precipitation_forecast_mm", 0.0)
            detected_risks.append(
                f"METEOROLOGICAL_ALERT: {risk_level} weather alert along route; max forecast precipitation {max_p:.1f} mm."
            )

        # 3. Correlate Landslide Hazards with Weather API to Assess Research-Model Trigger Conditions
        weather_points = w_res.get("weather_points", [])
        hazards = ls_res.get("hazards", [])
        active_warnings_count = 0
        warning_level_ranks = {"NONE": 0, "LEVEL_1_WATCH": 1, "LEVEL_2_ALERT": 2, "LEVEL_3_EVACUATION": 3}
        highest_warning_level = "NONE"

        for h in hazards:
            rec = h.get("record", {})
            h_lat = rec.get("latitude")
            h_lon = rec.get("longitude")
            trigger_mm = rec.get("trigger_rainfall_mm", 75.0) or 75.0
            trigger_src = rec.get("trigger_rainfall_source", "NBRO_EMPIRICAL_WATCH_THRESHOLD")
            trig_status = rec.get("trigger_rainfall_status", "AVAILABLE")
            district = rec.get("district", "Hill Country")
            inc_type = rec.get("incident_type", "Landslide")
            event_date = rec.get("event_date")

            # Resolve local forecast rainfall near this hazard
            loc_rain_mm = 0.0
            if weather_points and h_lat is not None and h_lon is not None:
                closest_wp = min(
                    weather_points,
                    key=lambda wp: haversine_distance_m(h_lat, h_lon, wp.get("latitude", 0), wp.get("longitude", 0))
                )
                loc_rain_mm = float(closest_wp.get("precipitation_mm", 0.0) or 0.0)
            elif w_res.get("max_precipitation_forecast_mm") is not None:
                loc_rain_mm = float(w_res.get("max_precipitation_forecast_mm", 0.0))

            ratio = (loc_rain_mm / trigger_mm) if trigger_mm > 0 else 0.0
            pct = round(ratio * 100.0, 1)

            # Model Early Warning Level Assessment
            if loc_rain_mm >= trigger_mm or loc_rain_mm >= 150.0:
                w_level = "LEVEL_3_EVACUATION"
                w_title = "Research Model: High Trigger Rainfall Condition"
                w_status = "ACTIVE_LANDSLIDE_WARNING"
                is_active = True
                msg = (
                    f"CRITICAL WARNING (Research Model): Current/forecast rainfall ({loc_rain_mm:.1f} mm) meets or exceeds historical "
                    f"failure trigger ({trigger_mm:.1f} mm) recorded during the {event_date or 'historical'} {inc_type} "
                    f"in {district}. Research model indicates elevated risk of slope reactivation."
                )
            elif loc_rain_mm >= (trigger_mm * 0.75) or loc_rain_mm >= 100.0:
                w_level = "LEVEL_2_ALERT"
                w_title = "Research Model: Amber Alert Condition"
                w_status = "ACTIVE_LANDSLIDE_WARNING"
                is_active = True
                msg = (
                    f"AMBER ALERT (Research Model): Current/forecast rainfall ({loc_rain_mm:.1f} mm) has reached {pct}% of historical failure "
                    f"trigger threshold ({trigger_mm:.1f} mm) in {district}. Slope saturation approaching critical limit."
                )
            elif loc_rain_mm >= (trigger_mm * 0.50) or loc_rain_mm >= 75.0:
                w_level = "LEVEL_1_WATCH"
                w_title = "Research Model: Yellow Watch Condition"
                w_status = "POTENTIAL_RISK_WATCH"
                is_active = True
                msg = (
                    f"YELLOW WATCH (Research Model): Current/forecast rainfall ({loc_rain_mm:.1f} mm) exceeds NBRO 75mm baseline "
                    f"({pct}% of trigger {trigger_mm:.1f} mm) in {district}. Watch for rockfalls and slope seepage."
                )
            else:
                w_level = "NONE"
                w_title = "Normal / Low Landslide Risk"
                w_status = "NO_CURRENT_WARNING"
                is_active = False
                msg = (
                    f"NO ACTIVE WARNING (Research Model): Historical failure occurred under {trigger_mm:.1f} mm rainfall ({trigger_src}). "
                    f"Current forecast is {loc_rain_mm:.1f} mm ({pct}% of trigger). Ground conditions currently below warning thresholds."
                )

            h["historical_trigger_rainfall_mm"] = round(trigger_mm, 1) if trigger_mm is not None else None
            h["trigger_rainfall_source"] = trigger_src
            h["trigger_rainfall_status"] = trig_status
            h["current_forecast_rainfall_mm"] = round(loc_rain_mm, 1)
            h["rainfall_trigger_percentage"] = pct
            h["warning_level"] = w_level
            h["warning_title"] = w_title
            h["warning_status"] = w_status
            h["is_warning_active"] = is_active
            h["warning_message"] = msg
            h["is_official_government_warning"] = False

            if is_active:
                active_warnings_count += 1
                if warning_level_ranks[w_level] > warning_level_ranks[highest_warning_level]:
                    highest_warning_level = w_level
                detected_risks.append(
                    f"ACTIVE_LANDSLIDE_{w_level}: [Research Model] {w_title} in {district} — Forecast rain {loc_rain_mm:.1f}mm vs trigger threshold {trigger_mm:.1f}mm ({pct}%)."
                )

        ls_res["active_warnings_count"] = active_warnings_count
        ls_res["highest_warning_level"] = highest_warning_level

        # 4. Determine Unified Assessment Status
        if ls_status == "RISK_DATA_UNAVAILABLE" and w_status == "RISK_DATA_UNAVAILABLE":
            unified_status = "RISK_DATA_UNAVAILABLE"
        elif ls_status == "RISK_DATA_UNAVAILABLE" or w_status in ("RISK_DATA_UNAVAILABLE", "RISK_ASSESSMENT_PARTIAL"):
            if detected_risks:
                unified_status = "RISK_DETECTED"
            else:
                unified_status = "RISK_ASSESSMENT_PARTIAL"
        elif ls_status == "RISK_DETECTED" or w_status == "RISK_DETECTED" or active_warnings_count > 0:
            unified_status = "RISK_DETECTED"
        elif w_status == "DATA_STALE":
            unified_status = "DATA_STALE"
        else:
            unified_status = "NO_RISK_DETECTED"

        # 5. Calculate Unified Route Environmental Risk Score (0-100)
        # Component 1: Landslide Proximity & Density (0-40)
        score_ls = 0
        if ls_res.get("hazard_count", 0) > 0:
            closest_m = ls_res.get("closest_hazard_distance_m")
            if closest_m is not None:
                if closest_m <= 250.0:
                    score_ls += 25
                elif closest_m <= 500.0:
                    score_ls += 20
                elif closest_m <= 1000.0:
                    score_ls += 12
                elif closest_m <= 1500.0:
                    score_ls += 6
            score_ls += min(15, ls_res["hazard_count"] * 3)
            score_ls = min(40, score_ls)

        # Component 2: Meteorological Severity (0-30)
        score_w = 0
        w_risk_level = w_res.get("overall_risk_level", "NONE")
        max_p = float(w_res.get("max_precipitation_forecast_mm", 0.0) or 0.0)
        if w_res.get("available", False):
            if w_risk_level == "HIGH":
                score_w = min(30, 22 + int(max_p / 15.0))
            elif w_risk_level == "MODERATE":
                score_w = min(20, 12 + int(max_p / 10.0))
            elif max_p > 0.0:
                score_w = min(10, max(2, int(max_p / 5.0)))
        score_w = min(30, score_w)

        # Component 3: Compound Rainfall-Trigger Landslide Warning (0-30)
        score_compound = 0
        if highest_warning_level == "LEVEL_3_EVACUATION":
            score_compound = 30
        elif highest_warning_level == "LEVEL_2_ALERT":
            score_compound = 20
        elif highest_warning_level == "LEVEL_1_WATCH":
            score_compound = 10

        total_risk_score = min(100, score_ls + score_w + score_compound)

        if unified_status == "RISK_DATA_UNAVAILABLE":
            total_risk_score = 0
            risk_rating = "UNKNOWN"
        elif total_risk_score < 25:
            risk_rating = "LOW"
        elif total_risk_score < 50:
            risk_rating = "MODERATE"
        elif total_risk_score < 75:
            risk_rating = "ELEVATED"
        else:
            risk_rating = "HIGH"

        model_category = self.get_model_risk_category(total_risk_score)

        risk_score_breakdown = {
            "landslide_proximity_score": score_ls,
            "weather_severity_score": score_w,
            "compound_trigger_score": score_compound,
            "total_score": total_risk_score,
            "max_possible_score": 100,
            "active_landslide_warnings_count": active_warnings_count,
            "highest_warning_level": highest_warning_level,
            "risk_rating": risk_rating,
            "model_risk_category": model_category,
        }

        # 6. Formulate Clean Real-Time Landslide Warning & Real-Time Weather Risk Objects
        max_corridor_rain = float(w_res.get("max_precipitation_forecast_mm", 0.0) or 0.0)
        is_warn = (active_warnings_count > 0)
        current_landslide_warning = {
            "is_warning_active": is_warn,
            "warning_level": highest_warning_level,
            "warning_title": (
                "Research Model: High Trigger Rainfall Condition" if highest_warning_level == "LEVEL_3_EVACUATION" else (
                    "Research Model: Amber Alert Condition" if highest_warning_level == "LEVEL_2_ALERT" else (
                        "Research Model: Yellow Watch Condition" if highest_warning_level == "LEVEL_1_WATCH" else "Normal Slope Stability"
                    )
                )
            ),
            "status": "ACTIVE_LANDSLIDE_WARNING" if is_warn else "NO_ACTIVE_WARNING",
            "is_official_government_warning": False,
            "official_warning_status": official_status,
            "disclaimer": "Advisory generated by research environmental risk model; does not constitute an official NBRO/DMC evacuation order.",
            "corridor_forecast_rainfall_mm": round(max_corridor_rain, 1),
            "nbro_threshold_baseline_mm": 75.0,
            "slope_zones_in_corridor": ls_res.get("hazard_count", 0),
            "polygon_zones_in_corridor": ls_res.get("polygon_count", 0),
            "incident_zones_in_corridor": ls_res.get("incident_count", 0),
            "closest_slope_distance_m": ls_res.get("closest_hazard_distance_m"),
            "closest_polygon_distance_m": ls_res.get("closest_polygon_distance_m"),
            "warning_message": (
                f"MODEL ALERT: Forecast rainfall ({max_corridor_rain:.1f} mm) reaches critical slope failure threshold in this corridor. Route diversion advised."
                if highest_warning_level == "LEVEL_3_EVACUATION" else (
                    f"MODEL AMBER: Forecast rainfall ({max_corridor_rain:.1f} mm) approaching critical saturation limit in hill country. Be prepared to divert."
                    if highest_warning_level == "LEVEL_2_ALERT" else (
                        f"MODEL WATCH: Forecast rainfall ({max_corridor_rain:.1f} mm) exceeds NBRO 75mm baseline. Be vigilant for rockfalls."
                        if highest_warning_level == "LEVEL_1_WATCH" else (
                            f"NO ACTIVE MODEL TRIGGER: Real-time rainfall along this route ({max_corridor_rain:.1f} mm) is below the NBRO 75mm baseline threshold."
                            if ls_status == "RISK_DETECTED" else "NO LANDSLIDE RISK: Route traverses low-lying terrain with no documented slope instability hazards."
                        )
                    )
                )
            ),
        }

        wp_list = w_res.get("weather_points", [])
        primary_wp = wp_list[0] if wp_list else {}
        weather_descriptions = primary_wp.get("weather_descriptions", ["Clear / Normal"]) if primary_wp else ["Clear / Normal"]
        temp_range = primary_wp.get("temperature_range_c", [22.0, 29.0]) if primary_wp else [22.0, 29.0]
        w_overall_risk = w_res.get("overall_risk_level", "NONE")

        realtime_weather_risk = {
            "overall_risk_level": w_overall_risk,
            "max_forecast_precipitation_mm": round(max_corridor_rain, 1),
            "weather_condition": ", ".join(weather_descriptions).title() if weather_descriptions else "Clear / Normal",
            "temperature_range_c": temp_range,
            "is_severe_alert": w_overall_risk in ("MODERATE", "HIGH"),
            "summary": w_res.get("summary", "Real-time weather checked across sampled corridor points."),
        }

        ls_res["current_landslide_warning"] = current_landslide_warning
        w_res["realtime_weather_risk"] = realtime_weather_risk

        # 7. Formulate Transparent Evidence & Limitations Statement
        evidence_parts = []
        if detected_risks:
            evidence_parts.append("Environmental risks identified from official datasets: " + " | ".join(detected_risks))
        else:
            evidence_parts.append("No active meteorological alerts or proximity to historical NBRO landslide records detected.")

        evidence_parts.append(
            "LIMITATIONS: NBRO landslide points represent recorded historical ground truth incidents, NOT active road closures. "
            "Weather evaluations are based on OpenWeatherMap 5-day forecasts. "
            "Absence of detected risk does not guarantee absolute safety against unforeseen localized ground movements. "
            "Disaster Management Centre (DMC) real-time flood warning feeds are NOT currently integrated."
        )

        evidence_text = " ".join(evidence_parts)

        # Research hypothesis formula metrics
        susc_val = min(100.0, float(score_ls * 2.5))
        r24_val = min(100.0, float(max_corridor_rain))
        w_score_val = min(100.0, float(score_w * 3.33))
        research_metrics = self.calculate_research_formula(
            landslide_susceptibility=susc_val,
            r24=r24_val,
            r72=0.0,
            r7=0.0,
            weather_score=w_score_val,
            w_ls=0.60,
            w_weather=0.40,
        )
        safety_indicator = round(100.0 - float(total_risk_score), 1)

        # Route segment aggregation if segments provided
        seg_aggregation = {}
        elevated_time = 0.0
        highest_seg = {}
        if segments:
            seg_aggregation = self.calculate_route_risk_aggregation(segments)
            elevated_time = seg_aggregation.get("time_spent_in_elevated_risk_min", 0.0)
            highest_seg = seg_aggregation.get("highest_risk_segment") or {}

        confidence = (
            "HIGH_CONFIDENCE"
            if unified_status in ("RISK_DETECTED", "NO_RISK_DETECTED")
            else ("DATA_STALE" if unified_status == "DATA_STALE" else "PARTIAL_CONFIDENCE")
        )

        return EnvironmentalRiskAssessment(
            route_id=route_id,
            status=unified_status,
            environmental_risk_score=total_risk_score,
            risk_rating=risk_rating,
            assessed_at_utc=assessed_at,
            detected_risks=detected_risks,
            landslide_summary=ls_res,
            weather_summary=w_res,
            dmc_status=self.dmc_adapter.get_status(),
            evidence_and_limitations=evidence_text,
            risk_score_breakdown=risk_score_breakdown,
            current_landslide_warning=current_landslide_warning,
            realtime_weather_risk=realtime_weather_risk,
            environmental_safety_indicator=safety_indicator,
            research_risk_metrics=research_metrics,
            model_risk_category=model_category,
            official_warning_status=official_status,
            official_warnings=official_active_records,
            time_spent_in_elevated_risk_min=elevated_time,
            highest_risk_segment=highest_seg,
            route_risk_aggregation=seg_aggregation,
            confidence_status=confidence,
        )


# Singleton instance
environmental_risk_service = EnvironmentalRiskService()
get_model_risk_category = EnvironmentalRiskService.get_model_risk_category
