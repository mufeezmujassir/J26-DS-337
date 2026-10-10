"""Google Places monitor for disruption detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from app.replanning.disruption_detection.utils import (
    get_env_api_key,
    load_config,
)

LOGGER = logging.getLogger(__name__)

FIND_URL = (
    "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
)
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

#: Fields requested from the Places Details endpoint.
FIELDS = (
    "place_id,name,business_status,current_opening_hours,"
    "rating,user_ratings_total"
)

CLOSED_STATUSES = frozenset(
    {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}
)

#: Review-volume thresholds for the crowd popularity proxy.
CROWD_HIGH_MIN = 1500
CROWD_MEDIUM_MIN = 150


class PlacesMonitor:
    """Polls Google Places for the status of a planned attraction."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or load_config("config.yaml")
        places_config = self.config.get("places", {})
        self.api_key_env = places_config.get(
            "api_key_env", "GOOGLE_PLACES_API_KEY"
        )
        self.timeout = places_config.get("timeout_seconds", 10)

    def monitor(
        self,
        place_name: str = "",
        place_id: str = "",
    ) -> Dict[str, Any]:
        """Fetch and reduce attraction status into a signal dict."""
        signal = self._empty_signal()
        api_key = get_env_api_key(self.api_key_env)

        if not api_key:
            LOGGER.warning(
                "Places monitor skipped: %s not set", self.api_key_env
            )
            return signal
        if not place_id and not place_name:
            LOGGER.warning("Places monitor skipped: no place name or id")
            return signal

        try:
            resolved_id = place_id or self._find_place_id(place_name, api_key)
            if not resolved_id:
                LOGGER.warning(
                    "Places monitor: no place id resolved for %r", place_name
                )
                return signal
            payload = self._fetch_details(resolved_id, api_key)
        except (requests.RequestException, ValueError) as exc:
            LOGGER.error("Places API request failed: %s", exc)
            return signal

        LOGGER.debug("Places API returned details for place id %s", resolved_id)
        return self._parse(payload)

    def _find_place_id(self, place_name: str, api_key: str) -> str:
        """Resolve a free-text attraction name to a Google place_id."""
        params = {
            "input": place_name,
            "inputtype": "textquery",
            "fields": "place_id",
            "key": api_key,
        }
        response = requests.get(FIND_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()

        candidates = payload.get("candidates") or []
        return str(candidates[0].get("place_id", "")) if candidates else ""

    def _fetch_details(self, place_id: str, api_key: str) -> Dict[str, Any]:
        """Fetch the Places Details payload for a place_id."""
        params = {
            "place_id": place_id,
            "fields": FIELDS,
            "key": api_key,
        }
        response = requests.get(
            DETAILS_URL, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json().get("result", {})

    def _parse(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce a Places Details result into the signal contract."""
        business_status = result.get("business_status", "OPERATIONAL")
        hours = result.get("current_opening_hours") or {}
        open_now = bool(hours.get("open_now", False))

        if business_status in CLOSED_STATUSES or not open_now:
            is_open = False
            closure_flag = True
        else:
            is_open = True
            closure_flag = False

        total_ratings = int(result.get("user_ratings_total", 0) or 0)
        if total_ratings >= CROWD_HIGH_MIN:
            crowd_level = "high"
        elif total_ratings >= CROWD_MEDIUM_MIN:
            crowd_level = "medium"
        else:
            crowd_level = "low"

        if not is_open:
            crowd_level = "low"
            capacity_issue = False
        else:
            capacity_issue = crowd_level == "high"

        LOGGER.info(
            "Places signal: open=%s closure=%s crowd=%s capacity_issue=%s",
            is_open,
            closure_flag,
            crowd_level,
            capacity_issue,
        )

        return {
            "is_open": is_open,
            "closure_flag": closure_flag,
            "capacity_issue": capacity_issue,
            "crowd_level": crowd_level,
        }

    @staticmethod
    def _empty_signal() -> Dict[str, Any]:
        """Degraded signal returned when the API cannot be reached."""
        return {
            "is_open": False,
            "closure_flag": False,
            "capacity_issue": False,
            "crowd_level": "low",
        }