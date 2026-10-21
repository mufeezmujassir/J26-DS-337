"""Configuration loader and helpers for preference elicitation."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = MODULE_DIR / "config.yaml"


def load_config(path: str = None) -> Dict[str, Any]:
    if path is None:
        path = str(DEFAULT_CONFIG_PATH)
    config_path = Path(path)
    if not config_path.exists():
        # try relative to cwd
        alt = Path.cwd() / path
        if alt.exists():
            config_path = alt
    if yaml is not None and config_path.suffix in (".yaml", ".yml"):
        try:
            with config_path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    # fallback minimal config
    return {
        "elicitation": {
            "max_turns": 5,
            "field_order": [
                "group_type",
                "trip_type",
                "vibe",
                "budget_per_day",
                "duration_days",
                "dates",
                "departure_point",
            ],
            "field_options": {
                "group_type": ["solo", "couple", "friends", "family"],
                "trip_type": [
                    "honeymoon",
                    "friends_trip",
                    "family",
                    "solo_adventure",
                    "cultural_pilgrimage",
                ],
                "vibe": ["relaxed", "active", "adventurous", "mixed", "cultural"],
            },
            "budget": {"min": 20, "max": 1000, "currency": "USD"},
            "duration": {"min_days": 1, "max_days": 30},
        },
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "model": "gemini-1.5-flash",
            "timeout_seconds": 10,
        },
        "state": {"backend": "redis", "ttl_hours": 24},
        "logging": {"level": "INFO"},
    }


def generate_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.utcnow()


def get_env_api_key(name: str) -> str:
    return os.environ.get(name) or os.environ.get(name.upper()) or ""


def call_gemini(prompt: str) -> str:
    """Call Gemini API. Returns text response or raises on failure."""
    api_key = get_env_api_key("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        # try to extract text
        if hasattr(resp, "text") and resp.text:
            return resp.text
        # candidates
        try:
            candidates = getattr(resp, "candidates", [])
            if candidates:
                content = getattr(candidates[0], "content", None)
                if content and getattr(content, "parts", None):
                    parts = content.parts
                    if parts and hasattr(parts[0], "text"):
                        return parts[0].text
        except Exception:
            pass
        return str(resp)
    except Exception as e:
        raise RuntimeError(f"Gemini call failed: {e}")


_BUDGET_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:usd|dollars?)?", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*(?:days?|nights?)", re.I)
_GROUP_RE = re.compile(r"\b(solo|couple|friends?|family)\b", re.I)
_TRIP_RE = re.compile(
    r"\b(honeymoon|friends\s*trip|family\s*trip|solo\s*adventure|cultural\s*pilgrimage)\b",
    re.I,
)
_VIBE_RE = re.compile(r"\b(relaxed|active|adventurous|mixed|cultural)\b", re.I)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", re.I)


def validate_field_value(field: str, value: str) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    if field == "group_type":
        return s.lower().replace(" ", "") in ("solo", "couple", "friends", "friend", "family")
    if field == "trip_type":
        vl = s.lower().replace(" ", "_")
        return vl in (
            "honeymoon",
            "friends_trip",
            "family",
            "solo_adventure",
            "cultural_pilgrimage",
        )
    if field == "vibe":
        return s.lower() in ("relaxed", "active", "adventurous", "mixed", "cultural")
    if field == "budget_per_day":
        try:
            v = float(re.sub(r"[^\d\.]", "", s))
            return 0 < v <= 10000
        except Exception:
            return False
    if field == "duration_days":
        try:
            v = int(re.sub(r"[^\d]", "", s))
            return 0 < v <= 365
        except Exception:
            return False
    if field == "dates":
        return bool(_DATE_RE.search(s))
    if field == "departure_point":
        return len(s) >= 2
    return True


def regex_extract_fallback(user_message: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    m = _BUDGET_RE.search(user_message)
    if m:
        try:
            fields["budget_per_day"] = float(m.group(1))
        except Exception:
            pass
    m = _DAYS_RE.search(user_message)
    if m:
        try:
            fields["duration_days"] = int(m.group(1))
        except Exception:
            pass
    m = _GROUP_RE.search(user_message)
    if m:
        g = m.group(1).lower()
        if g == "friends":
            g = "friends"
        fields["group_type"] = g
    m = _TRIP_RE.search(user_message)
    if m:
        fields["trip_type"] = m.group(1).lower().replace(" ", "_").replace("-", "_")
    m = _VIBE_RE.search(user_message)
    if m:
        fields["vibe"] = m.group(1).lower()
    dates = _DATE_RE.findall(user_message)
    if dates:
        fields["dates"] = {"raw": " ".join(dates)}
    # departure point heuristic: "from X", "leaving from X"
    md = re.search(r"(?:from|leaving\s+from|depart(?:ing)?\s+(?:from)?)\s+([A-Za-z][A-Za-z\s]+)", user_message, re.I)
    if md:
        fields["departure_point"] = md.group(1).strip()
    return fields
