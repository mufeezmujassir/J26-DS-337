"""Helper primitives for the Wandaraya Dynamic Replanning module."""

from __future__ import annotations

import copy
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import requests
import yaml

if TYPE_CHECKING:  # pragma: no cover
    from app.schemas.replanning import RevisedPlan

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "intent_preservation": {
        "strict_vibe": True,
        "strict_budget": True,
        "strict_bookings": True,
    },
    "intent_classifier": {
        "enabled": False,
        "model_filename": "intent_classifier_rf.pkl",
        "random_state": 42,
        "decision_threshold": 0.5,
        "label_noise_rate": 0.05,
        "hybrid": {
            "confirm_threshold": 0.7,
            "no_preserve_threshold": 0.4,
        },
    },
    "replanning": {
        "step_level": {"replace_scope": "single_activity"},
        "day_level": {"replace_scope": "full_day"},
        "plan_level": {
            "replace_scope": "from_disruption_point",
            "call_component2": True,
        },
    },
    "component1": {
        "api_url_env": "COMPONENT1_API_URL",
        "timeout_seconds": 10,
    },
    "component2": {
        "api_url_env": "COMPONENT2_API_URL",
        "timeout_seconds": 10,
    },
    "consistency": {
        "enforce_vibe": True,
        "enforce_budget": True,
        "enforce_bookings": True,
        "enforce_must_see": True,
    },
    "confirmation": {
        "require_user_confirmation": True,
        "default_next_action": "find_alternative",
    },
    "state": {
        "backend": "redis",
        "ttl_hours": 24,
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    },
}


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load ``config.yaml`` and merge it over the built-in defaults."""

    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    path_obj = config_path.expanduser()

    if not path_obj.is_file():
        raise FileNotFoundError(
            f"Dynamic replanning config not found: {path_obj}"
        )

    try:
        with path_obj.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        raise ValueError(
            f"Dynamic replanning config is not valid YAML: "
            f"{path_obj} ({error})"
        ) from error

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise ValueError(
            f"Dynamic replanning config must be a YAML mapping, got "
            f"{type(raw).__name__}: {path_obj}"
        )

    return deep_merge(DEFAULT_CONFIG, raw)


def deep_merge(
    base: Dict[str, Any],
    override: Dict[str, Any],
) -> Dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""

    merged = copy.deepcopy(base)

    for key, value in (override or {}).items():
        current = merged.get(key)

        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)

    return merged


def generate_id(prefix: str = "plan") -> str:
    """Return a short, unique identifier with an optional prefix."""

    return f"{prefix}_{uuid.uuid4().hex}"


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""

    return datetime.now(timezone.utc)


def format_revised_plan(plan: "RevisedPlan") -> str:
    """Render a :class:`RevisedPlan` as a readable multi-line string."""

    lines: List[str] = []

    lines.append(f"Revised plan {plan.plan_id}")
    lines.append(f"  original plan : {plan.original_plan_id}")
    lines.append(f"  disruption    : {plan.disruption_id}")
    lines.append(f"  severity      : {plan.severity}")

    affected = plan.affected_element

    lines.append(
        "  affected      : "
        f"{affected.activity_name} "
        f"(day={affected.day or 'n/a'}, "
        f"slot={affected.time_slot or 'n/a'}, "
        f"location={affected.location or 'n/a'})"
    )

    if plan.revised_activities:
        lines.append("  revised activities:")

        for index, activity in enumerate(plan.revised_activities, start=1):
            lines.append(
                f"    {index}. {activity.activity_name} "
                f"[{activity.time_slot}, {activity.duration}]"
            )
            lines.append(f"       reason: {activity.reason}")
    else:
        lines.append("  revised activities: (none)")

    preserved = ", ".join(plan.preserved_elements) or "none"

    lines.append(f"  preserved     : {preserved}")
    lines.append(
        "  confirmation  : "
        f"{'required' if plan.requires_confirmation else 'not required'}"
    )

    return "\n".join(lines)


def get_env_api_key(name: str) -> str:
    """Return a stripped environment value, or an empty string."""

    if not name:
        return ""

    return (os.getenv(name) or "").strip()


def call_component1_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call Component 1's Destination Agent with ``payload``."""

    return _call_component_api("component1", payload)


def call_component2_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call Component 2's Transport Agent with ``payload``."""

    return _call_component_api("component2", payload)


def _call_component_api(
    section: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Shared HTTP POST helper for both external component agents."""

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as error:
        LOGGER.error(
            "%s call aborted, config could not be loaded: %s",
            section,
            error,
        )
        return {}

    component_config = config.get(section, {}) or {}

    env_name = component_config.get("api_url_env", "")
    url = get_env_api_key(env_name)

    if not url:
        LOGGER.warning(
            "%s is not configured (env var %s is empty); "
            "returning no alternatives",
            section,
            env_name or "<unset>",
        )
        return {}

    timeout = component_config.get("timeout_seconds", 10)

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        LOGGER.error(
            "%s call to %s timed out after %ss",
            section,
            url,
            timeout,
        )
        return {}
    except requests.RequestException as error:
        LOGGER.error(
            "%s call to %s failed: %s",
            section,
            url,
            error,
        )
        return {}
    except ValueError as error:
        LOGGER.error(
            "%s returned a non-JSON body from %s: %s",
            section,
            url,
            error,
        )
        return {}

    if not isinstance(data, dict):
        LOGGER.error(
            "%s returned %s, expected a JSON object",
            section,
            type(data).__name__,
        )
        return {}

    LOGGER.debug("%s call to %s succeeded", section, url)

    return data


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """Apply the logging level/format from the config, if not already set."""

    config = config or {}

    logging_section = config.get("logging", {}) or {}

    level_name = str(logging_section.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = logging_section.get(
        "format",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.basicConfig(level=level, format=log_format)