"""Helper functions for the Wandaraya disruption detection module."""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union

import yaml

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[2]

TimeInput = Union[str, datetime]

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%H:%M",
)


def load_config(path: str) -> dict:
    """Load a YAML configuration file, resolving relative paths against the module directory."""
    candidate = Path(path)
    if not candidate.is_absolute():
        for base in (MODULE_DIR, Path.cwd()):
            resolved = base / candidate
            if resolved.is_file():
                candidate = resolved
                break

    if not candidate.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with candidate.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    if not isinstance(config, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")

    LOGGER.debug("Loaded configuration from %s", candidate)
    return config


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two GPS coordinates."""
    radius_km = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(radius_km * c, 3)


def _to_datetime(value: TimeInput) -> datetime:
    """Convert a datetime or parseable string into a timezone-aware datetime."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        parsed = None
        for fmt in _TIME_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"Unrecognised time value: {value!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def time_diff_minutes(start: TimeInput, end: TimeInput) -> int:
    """Return whole minutes between two times (end - start)."""
    delta = _to_datetime(end) - _to_datetime(start)
    return int(delta.total_seconds() // 60)


def get_env_api_key(name: str) -> str:
    """Read an API key from the environment, loading .env on first use."""
    if name not in os.environ and load_dotenv is not None:
        env_file = REPO_ROOT / ".env"
        if env_file.is_file():
            load_dotenv(env_file)

    value = os.environ.get(name, "")
    if not value:
        LOGGER.warning("Environment variable %s is not set or empty", name)
    return value


def format_disruption_log(disruption: Dict[str, Any]) -> str:
    """Render a disruption mapping as a single log-friendly line."""
    disruption_id = disruption.get("disruption_id", "?")
    severity = disruption.get("severity", "?")
    source = disruption.get("source", "?")
    confidence = disruption.get("confidence", 0.0)
    reason = disruption.get("reason") or {}

    if isinstance(reason, dict):
        short = reason.get("short", "")
    else:
        short = getattr(reason, "short", str(reason))

    return (
        f"{disruption_id} [{severity}/{source}] {short} "
        f"(conf={float(confidence):.2f})"
    )


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)