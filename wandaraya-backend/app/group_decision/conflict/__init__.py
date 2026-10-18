"""
 Rule-based Conflict Detector.
"""

from app.group_decision.conflict.rules import detect_conflicts
from app.group_decision.conflict.normalize import normalize_name, load_conflict_config
from app.group_decision.conflict.schemas import (
    PreferenceRecord,
    DestinationValue,
    ActivityValue,
    BudgetValue,
    ScheduleValue,
    ConflictOutput,
)

__all__ = [
    "detect_conflicts",
    "normalize_name",
    "load_conflict_config",
    "PreferenceRecord",
    "DestinationValue",
    "ActivityValue",
    "BudgetValue",
    "ScheduleValue",
    "ConflictOutput",
]
