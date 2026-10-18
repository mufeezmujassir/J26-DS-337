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

logger = logging.getLogger(__name__)


# ============================================================================
# Section 8: DMC (Disaster Management Centre) Future Integration Architecture
# ============================================================================

class DMCWarningAdapterInterface(ABC):
    """
    Abstract contract for future Disaster Management Centre (DMC) flood warning integration.
    
    Expected DMC Schema Requirements:
    - warning_id: Unique warning identifier (e.g., 'DMC-FL-2026-042')
    - hazard_type: Hazard classification ('FLOOD_MAJOR', 'FLOOD_MINOR', 'RESERVOIR_SPILL')
    - severity_level: Warning color code ('RED' - Evacuation/Impassable, 'AMBER' - Caution, 'YELLOW' - Watch)
    - river_basin: Affected drainage basin (e.g., 'Kelani Ganga', 'Kalu Ganga', 'Gin Ganga', 'Nilwala Ganga')
    - affected_ds_divisions: List of administrative divisions affected
    - geometry_wkt: Spatial polygon or bounding envelope of inundated flood plains
    - effective_from_utc: ISO-8601 issuance timestamp
    - expires_at_utc: ISO-8601 expiration or re-evaluation timestamp
    
    Spatial Association with Routes:
    When integrated, route segments intersecting the spatial polygon or passing within 
    basin buffer zones will be identified and flagged for avoidance or caution advisories.
    
    Prerequisites Blocking Live Connection:
    1. Public machine-readable API or CAP (Common Alerting Protocol) XML/JSON feed from DMC Sri Lanka.
    2. Real-time water-level gauge telemetry from the Department of Irrigation.
    3. Official geospatial shapefiles of active emergency flood declarations.
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
        # Returns empty list; does not fabricate fake warnings
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "status": self.status,
            "environmental_risk_score": self.environmental_risk_score,
            "risk_rating": self.risk_rating,
            "risk_score_breakdown": self.risk_score_breakdown,
            "current_landslide_warning": self.current_landslide_warning,
            "realtime_weather_risk": self.realtime_weather_risk,
            "assessed_at_utc": self.assessed_at_utc,
            "detected_risks": self.detected_risks,
            "landslide_assessment": self.landslide_summary,
            "weather_assessment": self.weather_summary,
            "nbro_database_status": self.landslide_summary.get("database_status", {}),
            "dmc_flood_warning_integration": self.dmc_status,
            "evidence_and_limitations": self.evidence_and_limitations,
        }


class EnvironmentalRiskService:
    def __init__(
        self,
        landslide_svc: Optional[LandslideService] = None,
        weather_svc: Optional[WeatherRiskService] = None,
        dmc_adapter: Optional[DMCWarningAdapterInterface] = None,
    ) -> None:
        self.landslide_service = landslide_svc or landslide_service
        self.weather_service = weather_svc or weather_risk_service
        self.dmc_adapter = dmc_adapter or DMCFutureAdapter()

    def assess_route(
        self,
        route_coordinates: List[Tuple[float, float]],
        route_id: Optional[str] = None,
        travel_date: Optional[date] = None,
        landslide_buffer_m: float = 1000.0,
    ) -> EnvironmentalRiskAssessment:
        """
        Executes unified environmental risk assessment across landslide and weather domains.
        Compares historical landslide trigger rainfall with live meteorological forecasts
        to determine active landslide warnings and calculate a unified 0-100 risk score.
        """
        assessed_at = datetime.now(timezone.utc).isoformat()
        detected_risks: List[str] = []

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

        # 3. Correlate Landslide Hazards with Weather API to Assess Active Landslide Warnings
        # Compares rainfall recorded at the time historical landslides occurred against
        # current/forecast rainfall at that location to determine active landslide warnings.
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

            # NBRO Early Warning Level Assessment
            if loc_rain_mm >= trigger_mm or loc_rain_mm >= 150.0:
                w_level = "LEVEL_3_EVACUATION"
                w_title = "NBRO Level 3: Landslide Evacuation Warning"
                w_status = "ACTIVE_LANDSLIDE_WARNING"
                is_active = True
                msg = (
                    f"CRITICAL WARNING: Current/forecast rainfall ({loc_rain_mm:.1f} mm) meets or exceeds historical "
                    f"failure trigger ({trigger_mm:.1f} mm) recorded during the {event_date or 'historical'} {inc_type} "
                    f"in {district}. High risk of slope reactivation."
                )
            elif loc_rain_mm >= (trigger_mm * 0.75) or loc_rain_mm >= 100.0:
                w_level = "LEVEL_2_ALERT"
                w_title = "NBRO Level 2: Landslide Amber Alert"
                w_status = "ACTIVE_LANDSLIDE_WARNING"
                is_active = True
                msg = (
                    f"AMBER ALERT: Current/forecast rainfall ({loc_rain_mm:.1f} mm) has reached {pct}% of historical failure "
                    f"trigger threshold ({trigger_mm:.1f} mm) in {district}. Slope saturation approaching critical limit."
                )
            elif loc_rain_mm >= (trigger_mm * 0.50) or loc_rain_mm >= 75.0:
                w_level = "LEVEL_1_WATCH"
                w_title = "NBRO Level 1: Landslide Yellow Watch"
                w_status = "POTENTIAL_RISK_WATCH"
                is_active = True
                msg = (
                    f"YELLOW WATCH: Current/forecast rainfall ({loc_rain_mm:.1f} mm) exceeds NBRO 75mm baseline "
                    f"({pct}% of historical trigger {trigger_mm:.1f} mm) in {district}. Watch for rockfalls and slope seepage."
                )
            else:
                w_level = "NONE"
                w_title = "Normal / Low Landslide Risk"
                w_status = "NO_CURRENT_WARNING"
                is_active = False
                msg = (
                    f"NO ACTIVE WARNING: Historical failure occurred under {trigger_mm:.1f} mm rainfall ({trigger_src}). "
                    f"Current forecast is {loc_rain_mm:.1f} mm ({pct}% of trigger). Ground conditions currently below warning thresholds."
                )

            h["historical_trigger_rainfall_mm"] = round(trigger_mm, 1)
            h["trigger_rainfall_source"] = trigger_src
            h["current_forecast_rainfall_mm"] = round(loc_rain_mm, 1)
            h["rainfall_trigger_percentage"] = pct
            h["warning_level"] = w_level
            h["warning_title"] = w_title
            h["warning_status"] = w_status
            h["is_warning_active"] = is_active
            h["warning_message"] = msg

            if is_active:
                active_warnings_count += 1
                if warning_level_ranks[w_level] > warning_level_ranks[highest_warning_level]:
                    highest_warning_level = w_level
                detected_risks.append(
                    f"ACTIVE_LANDSLIDE_{w_level}: {w_title} in {district} — Forecast rain {loc_rain_mm:.1f}mm vs historical failure trigger {trigger_mm:.1f}mm ({pct}%)."
                )

        ls_res["active_warnings_count"] = active_warnings_count
        ls_res["highest_warning_level"] = highest_warning_level

        # 4. Determine Unified Assessment Status
        # Requirements:
        # - RISK_DETECTED: Available evidence indicates environmental risk
        # - NO_RISK_DETECTED: Available data checked successfully and no configured risk detected
        # - RISK_ASSESSMENT_PARTIAL: Some sources assessed, but others unavailable
        # - RISK_DATA_UNAVAILABLE: No usable risk information available
        # - DATA_STALE: Available data older than freshness limit

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

        risk_score_breakdown = {
            "landslide_proximity_score": score_ls,
            "weather_severity_score": score_w,
            "compound_trigger_score": score_compound,
            "total_score": total_risk_score,
            "max_possible_score": 100,
            "active_landslide_warnings_count": active_warnings_count,
            "highest_warning_level": highest_warning_level,
            "risk_rating": risk_rating,
        }

        # 6. Formulate Clean Real-Time Landslide Warning & Real-Time Weather Risk Objects
        max_corridor_rain = float(w_res.get("max_precipitation_forecast_mm", 0.0) or 0.0)
        is_warn = (active_warnings_count > 0)
        current_landslide_warning = {
            "is_warning_active": is_warn,
            "warning_level": highest_warning_level,
            "warning_title": (
                "NBRO Level 3: Landslide Evacuation Warning" if highest_warning_level == "LEVEL_3_EVACUATION" else (
                    "NBRO Level 2: Landslide Amber Alert" if highest_warning_level == "LEVEL_2_ALERT" else (
                        "NBRO Level 1: Landslide Yellow Watch" if highest_warning_level == "LEVEL_1_WATCH" else "Normal Slope Stability"
                    )
                )
            ),
            "status": "ACTIVE_LANDSLIDE_WARNING" if is_warn else "NO_ACTIVE_WARNING",
            "corridor_forecast_rainfall_mm": round(max_corridor_rain, 1),
            "nbro_threshold_baseline_mm": 75.0,
            "slope_zones_in_corridor": ls_res.get("hazard_count", 0),
            "polygon_zones_in_corridor": ls_res.get("polygon_count", 0),
            "incident_zones_in_corridor": ls_res.get("incident_count", 0),
            "closest_slope_distance_m": ls_res.get("closest_hazard_distance_m"),
            "closest_polygon_distance_m": ls_res.get("closest_polygon_distance_m"),
            "warning_message": (
                f"CRITICAL WARNING: Forecast rainfall ({max_corridor_rain:.1f} mm) reaches critical slope failure threshold in this corridor. Immediate evacuation or route diversion advised."
                if highest_warning_level == "LEVEL_3_EVACUATION" else (
                    f"AMBER ALERT: Forecast rainfall ({max_corridor_rain:.1f} mm) approaching critical saturation limit in hill country. Be prepared to divert."
                    if highest_warning_level == "LEVEL_2_ALERT" else (
                        f"YELLOW WATCH: Forecast rainfall ({max_corridor_rain:.1f} mm) exceeds NBRO 75mm baseline. Be vigilant for rockfalls and slope seepage."
                        if highest_warning_level == "LEVEL_1_WATCH" else (
                            f"NO ACTIVE LANDSLIDE WARNING: Real-time rainfall along this route ({max_corridor_rain:.1f} mm) is well below the NBRO 75mm slope failure threshold. Hill slopes are currently stable under prevailing weather."
                            if ls_status == "RISK_DETECTED" else "NO LANDSLIDE RISK: Route traverses low-lying/coastal terrain with no documented slope instability hazards."
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
        )


# Singleton instance
environmental_risk_service = EnvironmentalRiskService()
