"""Rule-based triggers for disruption detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.replanning.disruption_detection.utils import load_config

LOGGER = logging.getLogger(__name__)

#: Module-level configuration (thresholds come from config.yaml).
_CONFIG = load_config("config.yaml")

RAIN_THRESHOLD_HOURS = _CONFIG["weather"].get("rain_threshold_hours", 3)
GPS_DEVIATION_THRESHOLD_KM = _CONFIG["gps"].get("deviation_threshold_km", 5)
DELAY_THRESHOLD_MINUTES = _CONFIG["gps"].get(
    "delay_threshold_minutes", 60
)
MULTI_CLOSURE_COUNT = 2
COMPLAINT_SCORE_THRESHOLD = 0.7


def _get(signals: Dict[str, Any], *path: str, default: Any = None) -> Any:
    """Safe nested lookup over the merged signal dictionary."""
    current: Any = signals
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


@dataclass(frozen=True)
class Rule:
    """A declarative, rule-based disruption trigger."""

    name: str
    severity: str
    source: str
    category: Any
    condition: Callable[[Dict[str, Any]], bool]
    describe: Callable[[Dict[str, Any]], Dict[str, str]]


def _complaint_category(signals: Dict[str, Any]) -> str:
    """Map the complaint signal category into the schema vocabulary."""
    category = _get(signals, "complaint", "category", default="other")
    return "user_report" if category == "other" else category


RULES: List[Rule] = [
    Rule(
        name="rain_3h_outdoor",
        severity="step",
        source="weather",
        category="weather",
        condition=lambda s: (
            _get(s, "weather", "rain_duration_hours", default=0.0)
            > RAIN_THRESHOLD_HOURS
            and _get(s, "context", "is_outdoor", default=False) is True
        ),
        describe=lambda s: {
            "short": "Heavy rain ahead",
            "description": (
                f"Rain expected for "
                f"{_get(s, 'weather', 'rain_duration_hours', default=0.0):.1f}h "
                "during an outdoor activity"
            ),
            "details": (
                f"rule=rain_3h_outdoor "
                f"rain_duration_hours="
                f"{_get(s, 'weather', 'rain_duration_hours', default=0.0)} "
                f"is_outdoor={_get(s, 'context', 'is_outdoor', default=False)}"
            ),
        },
    ),
    Rule(
        name="attraction_closed",
        severity="step",
        source="places",
        category="attraction",
        condition=lambda s: _get(s, "places", "is_open", default=True)
        is False,
        describe=lambda s: {
            "short": "Attraction closed",
            "description": "Planned attraction is currently closed",
            "details": "rule=attraction_closed is_open=False",
        },
    ),
    Rule(
        name="multi_closure",
        severity="day",
        source="places",
        category="attraction",
        condition=lambda s: _get(
            s, "context", "closures_today", default=0
        )
        >= MULTI_CLOSURE_COUNT,
        describe=lambda s: {
            "short": "Multiple closures today",
            "description": (
                "Two or more planned attractions are closed today"
            ),
            "details": (
                f"rule=multi_closure "
                f"closures_today={_get(s, 'context', 'closures_today', default=0)}"
            ),
        },
    ),
    Rule(
        name="gps_off_route",
        severity="step",
        source="gps",
        category="transport",
        condition=lambda s: _get(s, "gps", "gps_deviation_km", default=0.0)
        > GPS_DEVIATION_THRESHOLD_KM,
        describe=lambda s: {
            "short": "Off planned route",
            "description": "GPS position deviates too far from the planned route",
            "details": (
                f"rule=gps_off_route "
                f"gps_deviation_km={_get(s, 'gps', 'gps_deviation_km', default=0.0)}"
            ),
        },
    ),
    Rule(
        name="time_delay_major",
        severity="day",
        source="gps",
        category="transport",
        condition=lambda s: _get(
            s, "gps", "time_delay_minutes", default=0
        )
        > DELAY_THRESHOLD_MINUTES,
        describe=lambda s: {
            "short": "Major schedule delay",
            "description": "Running more than 60 minutes behind schedule",
            "details": (
                f"rule=time_delay_major "
                f"time_delay_minutes="
                f"{_get(s, 'gps', 'time_delay_minutes', default=0)}"
            ),
        },
    ),
    Rule(
        name="complaint_detected",
        severity="step",
        source="complaint",
        category=_complaint_category,
        condition=lambda s: _get(
            s, "complaint", "complaint_score", default=0.0
        )
        > COMPLAINT_SCORE_THRESHOLD,
        describe=lambda s: {
            "short": "Complaint detected",
            "description": "Group chat complaint score exceeded threshold",
            "details": (
                f"rule=complaint_detected "
                f"complaint_score="
                f"{_get(s, 'complaint', 'complaint_score', default=0.0):.2f} "
                f"keywords={_get(s, 'complaint', 'keywords_found', default=[])}"
            ),
        },
    ),
    Rule(
        name="change_request_detected",
        severity="day",
        source="complaint",
        category="user_report",
        condition=lambda s: _get(
            s, "complaint", "change_request", default=False
        )
        is True,
        describe=lambda s: {
            "short": "Trip change requested",
            "description": "A group member requested a change to the plan",
            "details": "rule=change_request_detected change_request=True",
        },
    ),
    Rule(
        name="city_change_required",
        severity="plan",
        source="complaint",
        category="user_report",
        condition=lambda s: (
            _get(s, "context", "hotel_overbooked", default=False) is True
            or _get(s, "context", "city_change_requested", default=False)
            is True
        ),
        describe=lambda s: {
            "short": "City change required",
            "description": (
                "Hotel overbooked or the group requested a move to another city"
            ),
            "details": (
                f"rule=city_change_required "
                f"hotel_overbooked="
                f"{_get(s, 'context', 'hotel_overbooked', default=False)} "
                f"city_change_requested="
                f"{_get(s, 'context', 'city_change_requested', default=False)}"
            ),
        },
    ),
]

_RULES_BY_NAME = {rule.name: rule for rule in RULES}


def apply_rules(signals: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evaluate every rule against the merged signals and return fired triggers."""
    triggered: List[Dict[str, Any]] = []

    for rule in RULES:
        try:
            fired = rule.condition(signals)
        except Exception as exc:
            LOGGER.error("Rule %s raised while evaluating: %s", rule.name, exc)
            continue

        if fired:
            category = rule.category
            if callable(category):
                category = category(signals)
            reason = rule.describe(signals)

            LOGGER.info("Rule fired: %s (severity=%s)", rule.name, rule.severity)
            triggered.append(
                {
                    "name": rule.name,
                    "severity": rule.severity,
                    "source": rule.source,
                    "category": category,
                    "reason": reason,
                }
            )

    return triggered


def get_rule(name: str) -> Optional[Rule]:
    """Look up a rule by name."""
    return _RULES_BY_NAME.get(name)