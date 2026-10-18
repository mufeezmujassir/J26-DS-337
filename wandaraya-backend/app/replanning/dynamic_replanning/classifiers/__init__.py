"""ML classifiers and evaluation utilities for the intent-preservation module.

Builds the frozen intent dataset, trains the production Random Forest, and
provides shared constants used by evaluation and ablation scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Paths
MODULE_DIR: Path = Path(__file__).resolve().parents[1]
REPO_ROOT: Path = Path(__file__).resolve().parents[4]

DATA_DIR: Path = REPO_ROOT / "data" / "replanning" / "intent"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
MODEL_DIR: Path = MODULE_DIR / "model_files"

RAW_ATTRACTIONS_FILENAME = "sri_lankan_attractions.jsonl"
MODEL_FILENAME = "intent_classifier_rf.pkl"

# Labels
LABEL_PRESERVED = 1
LABEL_BROKEN = 0
LABELS: tuple[int, int] = (LABEL_BROKEN, LABEL_PRESERVED)
LABEL_NAMES: Dict[int, str] = {
    LABEL_PRESERVED: "preserved",
    LABEL_BROKEN: "broken",
}

# Features (canonical model order)
FEATURE_NAMES: tuple[str, ...] = (
    "vibe_match",
    "budget_diff_ratio",
    "bookings_preserved_ratio",
    "must_see_preserved_ratio",
    "time_shift_minutes",
    "activity_count_change",
    "location_distance_km",
    "num_activities_changed",
    "ratio_activities_changed",
    "anchor_age_minutes",
    "num_turns_since_anchor",
    "user_explicitly_changed_vibe",
    "user_explicitly_changed_budget",
    "num_prior_replans",
)

# Broken-intent categories
BROKEN_VIBE_MISMATCH = "vibe_mismatch"
BROKEN_BUDGET_OVERRUN = "budget_overrun"
BROKEN_MISSING_BOOKING = "missing_booking"
BROKEN_MISSING_MUST_SEE = "missing_must_see"
BROKEN_TIME_SHIFT = "time_shift"
BROKEN_LOCATION_SHIFT = "location_shift"
BROKEN_MULTIPLE_MINOR = "multiple_minor"

BROKEN_TYPES: tuple[str, ...] = (
    BROKEN_VIBE_MISMATCH,
    BROKEN_BUDGET_OVERRUN,
    BROKEN_MISSING_BOOKING,
    BROKEN_MISSING_MUST_SEE,
    BROKEN_TIME_SHIFT,
    BROKEN_LOCATION_SHIFT,
    BROKEN_MULTIPLE_MINOR,
)

# Personas
PERSONA_ADVENTURE = "Adventure Seeker"
PERSONA_CULTURAL = "Cultural Explorer"
PERSONA_FAMILY = "Family"
PERSONA_BUDGET = "Budget"

PERSONAS: tuple[str, ...] = (
    PERSONA_ADVENTURE,
    PERSONA_CULTURAL,
    PERSONA_FAMILY,
    PERSONA_BUDGET,
)

PERSONA_CATEGORIES: Dict[str, tuple[str, ...]] = {
    PERSONA_ADVENTURE: (
        "Nature & Landscapes",
        "Wildlife & Safari",
        "Photography & Scenic Spots",
    ),
    PERSONA_CULTURAL: (
        "History & Archaeology",
        "Culture & Heritage",
        "Religious & Spiritual",
    ),
    PERSONA_FAMILY: (
        "Beaches & Coastal",
        "Nature & Landscapes",
        "Photography & Scenic Spots",
        "Urban & City Attractions",
    ),
    PERSONA_BUDGET: (
        "History & Archaeology",
        "Nature & Landscapes",
        "Urban & City Attractions",
        "Culture & Heritage",
        "Religious & Spiritual",
        "Beaches & Coastal",
        "Uncategorized",
        "Wellness & Ayurveda",
        "Food & Culinary",
        "Photography & Scenic Spots",
        "Wildlife & Safari",
    ),
}

PERSONA_VIBE: Dict[str, str] = {
    PERSONA_ADVENTURE: "active",
    PERSONA_CULTURAL: "cultural",
    PERSONA_FAMILY: "relaxed",
    PERSONA_BUDGET: "mixed",
}

# Tolerances
TOLERANCE_FLEXI = "Flexi-Venturer"
TOLERANCE_PLAN_BOUND = "Plan-Bound"
TOLERANCES: tuple[str, ...] = (TOLERANCE_FLEXI, TOLERANCE_PLAN_BOUND)
PERSONA_TOLERANCE: Dict[str, str] = {
    PERSONA_ADVENTURE: TOLERANCE_FLEXI,
    PERSONA_CULTURAL: TOLERANCE_PLAN_BOUND,
    PERSONA_FAMILY: TOLERANCE_PLAN_BOUND,
    PERSONA_BUDGET: TOLERANCE_FLEXI,
}

# Sri-Lanka-specific trip-duration distribution
DURATION_VALUES: tuple[int, ...] = (3, 5, 7, 10, 14)
DURATION_WEIGHTS: tuple[float, ...] = (0.30, 0.30, 0.25, 0.10, 0.05)
DURATION_NAMES: Dict[int, str] = {
    3: "weekend_trip",
    5: "standard_package",
    7: "classic_full_week",
    10: "extended_tour",
    14: "grand_tour",
}

# Rule thresholds
BUDGET_OVERRUN_THRESHOLD = 0.10
TIME_SHIFT_THRESHOLD_MINUTES = 60
LOCATION_SHIFT_THRESHOLD_KM = 5.0
MIN_MINOR_CHANGES = 3
LABEL_NOISE_RATE = 0.05

# Cost and time defaults
HOTEL_COST_PER_NIGHT_USD = 40.0
DEFAULT_ACTIVITY_DURATION_MINUTES = 120
DEFAULT_OPENING_HOURS = "08:00-17:00"
TRANSPORT_COST_PER_DAY_USD = 25.0
TRAVEL_BUFFER_MINUTES = 30

# Generator constraints
MIN_ATTRACTIONS_PER_DISTRICT = 5
DECISION_THRESHOLD = 0.5

# Required raw-attraction fields
REQUIRED_ATTRACTION_FIELDS: tuple[str, ...] = (
    "attraction_id",
    "name",
    "district",
    "district_id",
    "category",
    "lat",
    "lng",
    "opening_hours",
    "entry_fee_usd",
    "is_outdoor",
    "duration_minutes",
)

# Supported vibes
VIBES: tuple[str, ...] = ("relaxed", "active", "cultural", "mixed")


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    """Load a JSON Lines file into a list of dictionaries."""
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
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {resolved}: {exc}"
                ) from exc
    return rows


def extract_features(row: Dict[str, Any]) -> List[float]:
    """Return the 14 model features from ``row`` in canonical order."""
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
    """Return a feature matrix for an iterable of dataset rows."""
    return [extract_features(row) for row in rows]


def label_value(row: Dict[str, Any]) -> int:
    """Return the integer label of ``row`` (defaults to broken)."""
    return int(row.get("label", LABEL_BROKEN))


__all__ = [
    "MODULE_DIR",
    "REPO_ROOT",
    "DATA_DIR",
    "RAW_DIR",
    "PROCESSED_DIR",
    "MODEL_DIR",
    "RAW_ATTRACTIONS_FILENAME",
    "MODEL_FILENAME",
    "LABEL_PRESERVED",
    "LABEL_BROKEN",
    "LABELS",
    "LABEL_NAMES",
    "FEATURE_NAMES",
    "BROKEN_TYPES",
    "BROKEN_VIBE_MISMATCH",
    "BROKEN_BUDGET_OVERRUN",
    "BROKEN_MISSING_BOOKING",
    "BROKEN_MISSING_MUST_SEE",
    "BROKEN_TIME_SHIFT",
    "BROKEN_LOCATION_SHIFT",
    "BROKEN_MULTIPLE_MINOR",
    "PERSONAS",
    "PERSONA_ADVENTURE",
    "PERSONA_CULTURAL",
    "PERSONA_FAMILY",
    "PERSONA_BUDGET",
    "PERSONA_CATEGORIES",
    "PERSONA_VIBE",
    "TOLERANCES",
    "TOLERANCE_FLEXI",
    "TOLERANCE_PLAN_BOUND",
    "PERSONA_TOLERANCE",
    "DURATION_VALUES",
    "DURATION_WEIGHTS",
    "DURATION_NAMES",
    "BUDGET_OVERRUN_THRESHOLD",
    "TIME_SHIFT_THRESHOLD_MINUTES",
    "LOCATION_SHIFT_THRESHOLD_KM",
    "MIN_MINOR_CHANGES",
    "LABEL_NOISE_RATE",
    "HOTEL_COST_PER_NIGHT_USD",
    "DEFAULT_ACTIVITY_DURATION_MINUTES",
    "DEFAULT_OPENING_HOURS",
    "VIBES",
    "load_jsonl",
    "extract_features",
    "feature_matrix",
    "label_value",
]