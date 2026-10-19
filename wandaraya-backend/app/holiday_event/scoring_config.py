"""Versioned, explicitly experimental holiday/event scoring configuration."""
from __future__ import annotations
from pathlib import Path
import yaml

DEFAULT_PATH = Path("config/holiday_event_scoring.yaml")

def load_scoring_config(path: str | Path = DEFAULT_PATH) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    weights = data.get("feature_weights", {})
    required = {"holiday", "poya", "verified_event", "interests"}
    if set(weights) != required or any(not isinstance(value, (int, float)) or value < 0 for value in weights.values()):
        raise ValueError("holiday-event scoring config has invalid feature weights")
    return data
