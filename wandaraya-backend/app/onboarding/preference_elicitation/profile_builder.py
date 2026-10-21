"""Build and update preference profiles."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from app.onboarding.preference_elicitation.models import PreferenceProfile
from app.onboarding.preference_elicitation.utils import now_utc


class ProfileBuilder:
    def build_profile(self, user_id: str, extracted_fields: Dict = None) -> PreferenceProfile:
        extracted_fields = extracted_fields or {}
        profile = PreferenceProfile(
            user_id=user_id,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        return self.update_profile(profile, extracted_fields)

    def update_profile(self, profile: PreferenceProfile, new_fields: Dict = None) -> PreferenceProfile:
        new_fields = new_fields or {}
        data = profile.model_dump()
        for k, v in new_fields.items():
            if v is None or v == "":
                continue
            # only update known fields if we want to be strict, but just set
            data[k] = v
        data["updated_at"] = now_utc()
        # rebuild
        try:
            updated = PreferenceProfile(**data)
        except Exception:
            # fallback manual
            updated = profile
            for k, v in new_fields.items():
                if hasattr(updated, k) and v is not None and v != "":
                    setattr(updated, k, v)
            updated.updated_at = now_utc()
        return updated

    def finalize_profile(self, profile: PreferenceProfile) -> PreferenceProfile:
        data = profile.model_dump()
        data["is_complete"] = True
        data["updated_at"] = now_utc()
        try:
            return PreferenceProfile(**data)
        except Exception:
            profile.is_complete = True
            profile.updated_at = now_utc()
            return profile

    def reset_profile(self, user_id: str) -> None:
        # no-op here; state manager handles storage
        return None
