"""ML classifiers and evaluation utilities for the disruption detection module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from app.replanning.disruption_detection.utils import MODULE_DIR, REPO_ROOT

DATA_DIR: Path = REPO_ROOT / "data" / "disruption_detection"
MODEL_DIR: Path = MODULE_DIR / "model_files"

FEATURE_NAMES: tuple[str, ...] = (
    "rain_duration_hours",
    "rain_intensity_score",
    "temperature_celsius",
    "heat_warning",
    "is_outdoor_activity",
    "closure_flag",
    "capacity_issue",
    "crowd_level_score",
    "complaint_score",
    "change_request",
    "gps_deviation_km",
    "time_delay_minutes",
    "num_affected_activities",
)

LABEL_NORMAL = "normal"
LABEL_DISRUPTION = "disruption"
LABELS: tuple[str, str] = (LABEL_NORMAL, LABEL_DISRUPTION)

SEVERITY_LEVELS: tuple[str, str, str] = ("step", "day", "plan")
SEVERITY_NONE = "none"

SOURCE_FEATURES: Dict[str, tuple[str, ...]] = {
    "weather": (
        "rain_duration_hours",
        "rain_intensity_score",
        "temperature_celsius",
        "heat_warning",
    ),
    "places": (
        "closure_flag",
        "capacity_issue",
        "crowd_level_score",
    ),
    "gps": (
        "gps_deviation_km",
        "time_delay_minutes",
    ),
    "complaint": (
        "complaint_score",
        "change_request",
    ),
}


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}")

    rows: List[Dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {resolved}: {exc}"
                ) from exc
    return rows


def extract_features(row: Dict[str, Any]) -> List[float]:
    vector: List[float] = []
    for name in FEATURE_NAMES:
        value = row.get(name, 0.0)
        if isinstance(value, bool):
            vector.append(float(int(value)))
        else:
            try:
                vector.append(float(value))
            except (TypeError, ValueError):
                vector.append(0.0)
    return vector


def feature_matrix(rows: Iterable[Dict[str, Any]]) -> List[List[float]]:
    return [extract_features(row) for row in rows]


def _score_to_rain_intensity(score: float) -> str:
    if score <= 0.0:
        return "none"
    if score < 0.4:
        return "light"
    if score < 0.7:
        return "heavy"
    return "storm"


def _score_to_crowd_level(score: float) -> str:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def row_to_signals(row: Dict[str, Any]) -> Dict[str, Any]:
    closure_flag = bool(row.get("closure_flag", 0))
    deviation = float(row.get("gps_deviation_km", 0.0))
    delay = int(row.get("time_delay_minutes", 0))
    complaint_score = float(row.get("complaint_score", 0.0))

    return {
        "weather": {
            "rain_duration_hours": float(row.get("rain_duration_hours", 0.0)),
            "rain_intensity": _score_to_rain_intensity(
                float(row.get("rain_intensity_score", 0.0))
            ),
            "temperature_celsius": float(
                row.get("temperature_celsius", 0.0)
            ),
            "heat_warning": bool(row.get("heat_warning", 0)),
        },
        "places": {
            "is_open": not closure_flag,
            "closure_flag": closure_flag,
            "capacity_issue": bool(row.get("capacity_issue", 0)),
            "crowd_level": _score_to_crowd_level(
                float(row.get("crowd_level_score", 0.0))
            ),
        },
        "gps": {
            "gps_deviation_km": deviation,
            "time_delay_minutes": delay,
            "off_route": deviation > 5.0,
            "running_late": delay > 60,
        },
        "complaint": {
            "complaint_score": complaint_score,
            "keywords_found": [],
            "category": "other",
            "change_request": bool(row.get("change_request", 0)),
        },
        "context": {
            "is_outdoor": bool(row.get("is_outdoor_activity", 0)),
            "closures_today": 1 if closure_flag else 0,
            "hotel_overbooked": False,
            "city_change_requested": False,
        },
    }


def severity_from_rows(rows: Sequence[Dict[str, Any]]) -> List[str]:
    return [str(row.get("severity", SEVERITY_NONE)) for row in rows]


__all__ = [
    "DATA_DIR",
    "MODEL_DIR",
    "FEATURE_NAMES",
    "LABELS",
    "LABEL_NORMAL",
    "LABEL_DISRUPTION",
    "SEVERITY_LEVELS",
    "SEVERITY_NONE",
    "SOURCE_FEATURES",
    "load_jsonl",
    "extract_features",
    "feature_matrix",
    "row_to_signals",
    "severity_from_rows",
]