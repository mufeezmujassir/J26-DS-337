"""Severity classification for triggered disruption rules."""

from __future__ import annotations

import logging
from typing import Dict, List

LOGGER = logging.getLogger(__name__)

#: Severity rank, weakest to strongest.
SEVERITY_ORDER = ("none", "step", "day", "plan")

_SEVERITY_RANK = {level: index for index, level in enumerate(SEVERITY_ORDER)}


def classify_severity(triggered_rules: List[Dict]) -> str:
    """Return the highest severity present among the triggered rules."""
    severities = [
        rule.get("severity") for rule in triggered_rules
        if _SEVERITY_RANK.get(rule.get("severity")) is not None
    ]

    if not severities:
        result = "none"
    else:
        result = max(
            severities, key=lambda value: _SEVERITY_RANK[value]
        )

    LOGGER.info(
        "Severity classified: %s (%d triggered rules)",
        result,
        len(triggered_rules),
    )
    return result


def rank(severity: str) -> int:
    """Return the numeric rank of a severity level (lowest is weakest)."""
    return _SEVERITY_RANK.get(severity, _SEVERITY_RANK["none"])