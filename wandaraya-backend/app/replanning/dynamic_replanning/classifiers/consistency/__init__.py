"""Cross-turn consistency classifier subpackage."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

# Paths ---------------------------------------------------------------------
MODULE_DIR: Path = Path(__file__).resolve().parents[2]  # dynamic_replanning
CLASSIFIERS_DIR: Path = Path(__file__).resolve().parents[1]
REPO_ROOT: Path = Path(__file__).resolve().parents[5]

CONSISTENCY_DATA_DIR: Path = REPO_ROOT / "data" / "replanning" / "consistency"
CONSISTENCY_RAW_DIR: Path = CONSISTENCY_DATA_DIR / "raw"
CONSISTENCY_PROCESSED_DIR: Path = CONSISTENCY_DATA_DIR / "processed"
CONSISTENCY_MODEL_DIR: Path = MODULE_DIR / "model_files"

CONSISTENCY_MODEL_FILENAME = "consistency_classifier_rf.pkl"
RAW_ATTRACTIONS_FILENAME = "sri_lankan_attractions.jsonl"

# Labels --------------------------------------------------------------------
LABEL_CONSISTENT = 0
LABEL_DRIFT = 1
LABELS: tuple[int, int] = (LABEL_CONSISTENT, LABEL_DRIFT)
LABEL_NAMES: Dict[int, str] = {
    LABEL_CONSISTENT: "consistent",
    LABEL_DRIFT: "drift",
}

# Features (canonical model order) ------------------------------------------
FEATURE_NAMES: tuple[str, ...] = (
    "num_prior_constraints",
    "num_conflicting_constraints",
    "last_vibe_mentioned",
    "last_budget_mentioned",
    "last_pace_preference",
    "plan_changes_since_last_turn",
    "num_turns",
    "avg_emotion_score",
    "num_explicit_confirmations",
    "num_explicit_rejections",
    "time_since_last_turn_minutes",
    "num_replans_this_trip",
)

# Vibes / pace encodings (mirrors the PPE module) ---------------------------
VIBES: tuple[str, ...] = ("relaxed", "active", "cultural", "mixed")
VIBE_ENCODING: Dict[str, int] = {v: i for i, v in enumerate(VIBES)}
VIBE_NONE = 4  # no vibe stated yet

PACES: tuple[str, ...] = ("slow", "moderate", "fast")
PACE_ENCODING: Dict[str, int] = {p: i for i, p in enumerate(PACES)}

# Drift scenarios -----------------------------------------------------------
DRIFT_CONSTRAINT_CONTRADICTION = "constraint_contradiction"
DRIFT_CONFIRMED_MUST_SEE_REMOVED = "confirmed_must_see_removed"
DRIFT_VIBE_CHANGED = "vibe_changed_without_approval"
DRIFT_BUDGET_EXCEEDED = "budget_exceeded"
DRIFT_NO_RUSHING_VIOLATED = "no_rushing_violated"
DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED = "rejected_alternative_reintroduced"
DRIFT_NONE = "none"

DRIFT_TYPES: tuple[str, ...] = (
    DRIFT_CONSTRAINT_CONTRADICTION,
    DRIFT_CONFIRMED_MUST_SEE_REMOVED,
    DRIFT_VIBE_CHANGED,
    DRIFT_BUDGET_EXCEEDED,
    DRIFT_NO_RUSHING_VIOLATED,
    DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED,
)

# Violation codes (shared between feature extractor and labeler) ------------
VIOLATION_VIBE_MISMATCH = "vibe_mismatch"
VIOLATION_BUDGET_EXCEEDED = "budget_exceeded"
VIOLATION_MUST_SEE_REMOVED = "must_see_removed"
VIOLATION_CONFIRMED_REMOVED = "confirmed_item_removed"
VIOLATION_REJECTION_REINTRODUCED = "rejected_alternative_reintroduced"
VIOLATION_NO_RUSHING = "no_rushing_violated"

VIOLATION_CODES: tuple[str, ...] = (
    VIOLATION_VIBE_MISMATCH,
    VIOLATION_BUDGET_EXCEEDED,
    VIOLATION_MUST_SEE_REMOVED,
    VIOLATION_CONFIRMED_REMOVED,
    VIOLATION_REJECTION_REINTRODUCED,
    VIOLATION_NO_RUSHING,
)

# Rule thresholds -----------------------------------------------------------
SCHEDULE_SHIFT_THRESHOLD_MINUTES = 60
LABEL_NOISE_RATE = 0.05
DECISION_THRESHOLD = 0.5

# Cost model (all raw entry fees are 0.0 in the source dump) ----------------
HOTEL_COST_PER_NIGHT_USD = 40.0
TRANSPORT_COST_PER_DAY_USD = 25.0
ACTIVITY_COST_RANGE_USD = (5.0, 45.0)
ACTIVITY_BUFFER_MINUTES = 45
ACTIVITY_BUFFER_RELAXED_MINUTES = 75  # "no rushing" pace

# Trip shape ----------------------------------------------------------------
TRIP_DAYS = 3
ACTIVITIES_PER_DAY_RANGE = (2, 4)
PLAN_DAILY_BUDGET_USD = {
    "Budget": 45.0,
    "Adventure Seeker": 90.0,
    "Cultural Explorer": 80.0,
    "Family": 110.0,
}

DEFAULT_SEED = 42
DECISION_THRESHOLD_NAME = "drift"

__all__ = [
    "MODULE_DIR",
    "CLASSIFIERS_DIR",
    "REPO_ROOT",
    "CONSISTENCY_DATA_DIR",
    "CONSISTENCY_RAW_DIR",
    "CONSISTENCY_PROCESSED_DIR",
    "CONSISTENCY_MODEL_DIR",
    "CONSISTENCY_MODEL_FILENAME",
    "RAW_ATTRACTIONS_FILENAME",
    "LABEL_CONSISTENT",
    "LABEL_DRIFT",
    "LABELS",
    "LABEL_NAMES",
    "FEATURE_NAMES",
    "VIBES",
    "VIBE_ENCODING",
    "VIBE_NONE",
    "PACES",
    "PACE_ENCODING",
    "DRIFT_TYPES",
    "DRIFT_NONE",
    "DRIFT_CONSTRAINT_CONTRADICTION",
    "DRIFT_CONFIRMED_MUST_SEE_REMOVED",
    "DRIFT_VIBE_CHANGED",
    "DRIFT_BUDGET_EXCEEDED",
    "DRIFT_NO_RUSHING_VIOLATED",
    "DRIFT_REJECTED_ALTERNATIVE_REINTRODUCED",
    "VIOLATION_CODES",
    "VIOLATION_VIBE_MISMATCH",
    "VIOLATION_BUDGET_EXCEEDED",
    "VIOLATION_MUST_SEE_REMOVED",
    "VIOLATION_CONFIRMED_REMOVED",
    "VIOLATION_REJECTION_REINTRODUCED",
    "VIOLATION_NO_RUSHING",
    "SCHEDULE_SHIFT_THRESHOLD_MINUTES",
    "LABEL_NOISE_RATE",
    "DECISION_THRESHOLD",
    "TRIP_DAYS",
    "DEFAULT_SEED",
]
