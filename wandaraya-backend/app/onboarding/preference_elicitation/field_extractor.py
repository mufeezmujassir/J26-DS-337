"""Identify missing fields in preference profile."""

from __future__ import annotations

from typing import List

from app.onboarding.preference_elicitation.models import PreferenceProfile
from app.onboarding.preference_elicitation.utils import load_config


DEFAULT_ORDER = [
    "group_type",
    "trip_type",
    "vibe",
    "budget_per_day",
    "duration_days",
    "dates",
    "departure_point",
]


class MissingFieldExtractor:
    def __init__(self, config: dict = None):
        self.config = config or load_config()
        elic = self.config.get("elicitation", {}) if isinstance(self.config, dict) else {}
        self.field_order = elic.get("field_order") or DEFAULT_ORDER

    def get_missing_fields(self, profile: PreferenceProfile) -> List[str]:
        missing = []
        for field in self.field_order:
            val = getattr(profile, field, None)
            if val is None:
                missing.append(field)
                continue
            # empty containers
            if isinstance(val, (list, dict)) and len(val) == 0:
                missing.append(field)
                continue
        return missing

    def get_next_missing_field(self, profile: PreferenceProfile) -> str:
        missing = self.get_missing_fields(profile)
        return missing[0] if missing else ""

    def is_profile_complete(self, profile: PreferenceProfile) -> bool:
        return len(self.get_missing_fields(profile)) == 0
