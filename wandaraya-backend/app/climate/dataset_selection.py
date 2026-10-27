"""Explicit version selection for overlapping climate records.

Selection requires a caller-supplied physical sample identity.  District
representatives and attraction coordinates must not be treated as identical
merely because they lie in the same district or near one another.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PILOT = 'nasa_power_daily_v2.10.0_2024_pilot'
HISTORICAL_BATCH01 = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch01'
HISTORICAL_BATCH02 = 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02'


def select_one_version(
    rows: Iterable[Mapping[str, Any]], *, dataset_version: str,
) -> list[Mapping[str, Any]]:
    """Select a single caller-approved dataset; reject duplicate sample-days.

    No coordinate equivalence, interpolation, or district-to-attraction
    inference is performed.  Requiring an explicit version prevents the 2024
    pilot and a historical batch from being combined as independent evidence.
    """
    if dataset_version not in {PILOT, HISTORICAL_BATCH01, HISTORICAL_BATCH02}:
        raise ValueError('unknown or unapproved climate dataset version')
    selected = []
    identities: set[tuple[str, str]] = set()
    for row in rows:
        if row.get('dataset_version') != dataset_version:
            continue
        sample_id, day = row.get('sample_id'), row.get('observation_date')
        if not sample_id or not day:
            raise ValueError('sample_id and observation_date are required')
        key = (str(sample_id), str(day))
        if key in identities:
            raise ValueError('duplicate sample-day in selected dataset')
        identities.add(key)
        selected.append(row)
    return selected
