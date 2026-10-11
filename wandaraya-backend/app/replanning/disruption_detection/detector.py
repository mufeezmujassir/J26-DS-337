"""Main disruption detection class."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from app.replanning.disruption_detection.complaint_detector import (
    ComplaintDetector,
)
from app.replanning.disruption_detection.fusion import FusionEngine
from app.replanning.disruption_detection.gps_monitor import GpsMonitor
from app.replanning.disruption_detection.places_monitor import PlacesMonitor
from app.replanning.disruption_detection.severity_classifier import (
    classify_severity,
)
from app.replanning.disruption_detection.trigger_rules import apply_rules
from app.replanning.disruption_detection.utils import (
    format_disruption_log,
    load_config,
    utc_now,
)
from app.replanning.disruption_detection.weather_monitor import WeatherMonitor
from app.schemas.disruption import (
    AffectedElement,
    Disruption,
    DisruptionReason,
)

LOGGER = logging.getLogger(__name__)

#: Minimum confidence assigned to a fired rule.
CONFIDENCE_FLOOR = 0.5

#: The four signal sources, in canonical evaluation order.
SOURCE_ORDER = ("weather", "places", "gps", "complaint")


class DisruptionDetector:
    """Rule-based detector that turns a trip context into disruptions."""

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config = load_config(config_path)
        self.weather_monitor = WeatherMonitor(self.config)
        self.places_monitor = PlacesMonitor(self.config)
        self.gps_monitor = GpsMonitor(self.config)
        self.complaint_detector = ComplaintDetector(self.config)
        self.fusion_engine = FusionEngine(self.config)

        LOGGER.info("DisruptionDetector initialised from %s", config_path)

    def detect(self, trip_context: dict) -> List[Disruption]:
        """Run detection without fusing a confirmation flag."""
        return self._run(trip_context, apply_fusion=False)

    def detect_and_fuse(self, trip_context: dict) -> List[Disruption]:
        """Run detection and attach fusion confirmation to each disruption."""
        return self._run(trip_context, apply_fusion=True)

    def check_source(
        self, source: str, trip_context: dict
    ) -> Dict[str, Any]:
        """Poll a single signal source for the given trip context."""
        context = trip_context or {}
        location = context.get("location") or {}
        place = context.get("place") or {}
        itinerary = context.get("itinerary") or {}

        if source == "weather":
            return self.weather_monitor.monitor(
                location.get("lat"), location.get("lon")
            )
        if source == "places":
            return self.places_monitor.monitor(
                place_name=place.get("name", ""),
                place_id=place.get("place_id", ""),
            )
        if source == "gps":
            return self.gps_monitor.monitor(
                latitude=location.get("lat"),
                longitude=location.get("lon"),
                scheduled_at=itinerary.get("scheduled_at"),
                actual_at=itinerary.get("actual_at"),
                planned_waypoints=context.get("route_waypoints"),
            )
        if source == "complaint":
            return self.complaint_detector.monitor(
                context.get("chat_message", "")
            )

        LOGGER.error("Unknown signal source requested: %s", source)
        return {}

    def _run(
        self,
        trip_context: dict,
        *,
        apply_fusion: bool,
    ) -> List[Disruption]:
        """Shared detection pipeline for detect and detect_and_fuse."""
        context = trip_context or {}
        itinerary = context.get("itinerary") or {}
        planner = context.get("planner") or {}

        signals = {
            "weather": self.check_source("weather", context) or {},
            "places": self.check_source("places", context) or {},
            "gps": self.check_source("gps", context) or {},
            "complaint": self.check_source("complaint", context) or {},
            "context": {
                "is_outdoor": itinerary.get("is_outdoor", False),
                "closures_today": planner.get("closures_today", 0),
                "hotel_overbooked": planner.get("hotel_overbooked", False),
                "city_change_requested": planner.get(
                    "city_change_requested", False
                ),
            },
        }

        triggered = apply_rules(signals)
        overall_severity = classify_severity(triggered)
        fused = self.fusion_engine.fuse(signals)

        LOGGER.info(
            "Detection pass: %d rule(s) fired, severity=%s, "
            "fused_score=%.3f",
            len(triggered),
            overall_severity,
            fused["score"],
        )

        if not triggered:
            LOGGER.info("No disruptions detected (severity=%s)", overall_severity)
            return []

        disruptions = self._build_disruptions(
            triggered, signals, itinerary, context, fused, apply_fusion
        )

        for disruption in disruptions:
            LOGGER.info(
                "Disruption %s",
                format_disruption_log(disruption.model_dump()),
            )
        return disruptions

    def _build_disruptions(
        self,
        triggered: List[Dict[str, Any]],
        signals: Dict[str, Any],
        itinerary: Dict[str, Any],
        context: Dict[str, Any],
        fused: Dict[str, Any],
        apply_fusion: bool,
    ) -> List[Disruption]:
        """Wrap triggered rules into Disruption objects."""
        place = context.get("place") or {}
        affected_element = AffectedElement(
            activity_name=itinerary.get("activity_name", ""),
            time_slot=itinerary.get("time_slot", ""),
            day=itinerary.get("day", ""),
            location=itinerary.get("location", "") or place.get("name", ""),
        )
        detected_at = utc_now()

        disruptions: List[Disruption] = []
        for rule in triggered:
            raw_confidence = self.fusion_engine.source_score(
                signals, rule["source"]
            )
            confidence = max(CONFIDENCE_FLOOR, raw_confidence)
            disruptions.append(
                Disruption(
                    disruption_id=(
                        f"{rule['name']}-{uuid.uuid4().hex[:8]}"
                    ),
                    source=rule["source"],
                    category=rule["category"],
                    severity=rule["severity"],
                    affected_element=affected_element,
                    reason=DisruptionReason(**rule["reason"]),
                    confidence=confidence,
                    requires_confirmation=(
                        fused["requires_confirmation"] if apply_fusion else False
                    ),
                    detected_at=detected_at,
                )
            )
        return disruptions


if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    MOCK_TRIP_CONTEXT = {
        "location": {"lat": 6.9271, "lon": 79.8612},
        "place": {"name": "Sigiriya Rock Fortress", "place_id": ""},
        "itinerary": {
            "day": "Day 2",
            "activity_name": "Sigiriya climb",
            "time_slot": "09:00-11:00",
            "location": "Sigiriya",
            "scheduled_at": "09:00",
            "actual_at": "09:05",
            "is_outdoor": True,
        },
        "route_waypoints": [{"lat": 7.9570, "lon": 80.7603}],
        "chat_message": (
            "we are late and stuck, the place is so crowded, "
            "let's cancel and go somewhere else instead"
        ),
        "planner": {
            "closures_today": 0,
            "hotel_overbooked": False,
            "city_change_requested": False,
        },
    }

    detector = DisruptionDetector()
    result = detector.detect_and_fuse(MOCK_TRIP_CONTEXT)

    print(
        json.dumps(
            [disruption.model_dump(mode="json") for disruption in result],
            indent=2,
        )
    )