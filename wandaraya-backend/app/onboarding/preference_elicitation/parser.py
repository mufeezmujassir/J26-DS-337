"""Parse user messages to extract preference fields."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from app.onboarding.preference_elicitation.utils import call_gemini, regex_extract_fallback

LOGGER = logging.getLogger(__name__)


class MessageParser:
    def parse(self, user_message: str) -> Dict[str, Any]:
        return self.extract_fields(user_message)

    def extract_fields(self, user_message: str) -> Dict[str, Any]:
        # Try Gemini first
        try:
            prompt = (
                "Extract travel preference fields from the user message. "
                "Return a JSON object with only the fields that are clearly mentioned. "
                "Possible keys: group_type (solo/couple/friends/family), "
                "trip_type (honeymoon/friends_trip/family/solo_adventure/cultural_pilgrimage), "
                "vibe (relaxed/active/adventurous/mixed/cultural), "
                "budget_per_day (number in USD), duration_days (integer), "
                "dates (object or string), departure_point (string), destination_shortlist (list). "
                f"User message: {user_message}\n\nReturn valid JSON only."
            )
            resp = call_gemini(prompt)
            # try to parse JSON from response
            # extract json block if present
            m = re.search(r"\{.*\}", resp, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                    return self.normalize_field_values(data if isinstance(data, dict) else {})
                except Exception:
                    pass
            try:
                data = json.loads(resp)
                return self.normalize_field_values(data if isinstance(data, dict) else {})
            except Exception:
                pass
        except Exception as e:
            LOGGER.warning(f"Gemini extraction failed, falling back to regex: {e}")

        # Fallback to regex
        try:
            fields = regex_extract_fallback(user_message)
            return self.normalize_field_values(fields)
        except Exception as e:
            LOGGER.warning(f"Regex extraction failed: {e}")
            return {}

    def normalize_field_values(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(fields, dict):
            return {}
        out: Dict[str, Any] = {}
        for k, v in fields.items():
            if v is None or v == "":
                continue
            kl = k.strip()
            # normalize common names
            if kl == "budget":
                kl = "budget_per_day"
            if kl == "duration":
                kl = "duration_days"
            if kl == "departure":
                kl = "departure_point"
            if kl == "group":
                kl = "group_type"
            if kl == "trip":
                kl = "trip_type"
            # normalize values
            if kl in ("group_type",):
                s = str(v).strip().lower().replace("-", " ")
                if s in ("friend", "friends"):
                    s = "friends"
                out[kl] = s
                continue
            if kl == "trip_type":
                s = str(v).strip().lower().replace(" ", "_").replace("-", "_")
                out[kl] = s
                continue
            if kl == "vibe":
                s = str(v).strip().lower()
                out[kl] = s
                continue
            if kl == "budget_per_day":
                try:
                    # extract number
                    m = re.search(r"(-?\d+(?:\.\d+)?)", str(v))
                    if m:
                        out[kl] = float(m.group(1))
                    else:
                        out[kl] = float(v)
                except Exception:
                    continue
                continue
            if kl == "duration_days":
                try:
                    m = re.search(r"(-?\d+)", str(v))
                    if m:
                        out[kl] = int(m.group(1))
                    else:
                        out[kl] = int(v)
                except Exception:
                    continue
                continue
            if kl == "dates":
                out[kl] = v if isinstance(v, dict) else {"raw": str(v)}
                continue
            if kl == "departure_point":
                out[kl] = str(v).strip()
                continue
            if kl == "destination_shortlist":
                if isinstance(v, list):
                    out[kl] = [str(x).strip() for x in v if str(x).strip()]
                elif isinstance(v, str):
                    out[kl] = [x.strip() for x in v.split(",") if x.strip()]
                continue
            out[kl] = v
        return out
