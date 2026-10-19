"""Decision metrics.

Provides member satisfaction and preference coverage metrics.

"""

from __future__ import annotations

from typing import Any
from app.group_decision.conflict.normalize import normalize_name
from app.group_decision.decision.schemas import PreferenceRecord


def _deduplicate_records(records: list[Any], category: str | None = None) -> dict[str, dict[str, str]]:
    """Extract latest stance per member and normalized option.

    Returns:
        Mapping of member -> {normalized_option: latest_stance}
    """
    member_stances: dict[str, dict[str, str]] = {}

    for raw in records:
        if isinstance(raw, PreferenceRecord):
            rec = raw
        else:
            rec = PreferenceRecord.model_validate(raw)

        if category is not None and rec.category != category:
            continue

        # Extract option name for Destination or Activity
        val = rec.value
        opt_raw = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else None)
        if not opt_raw:
            continue

        canon_opt = normalize_name(opt_raw, category=rec.category)
        if rec.member not in member_stances:
            member_stances[rec.member] = {}

        # Latest record overwrites earlier ones
        member_stances[rec.member][canon_opt] = rec.stance

    return member_stances


def member_satisfaction(
    records: list[Any],
    chosen: str | None,
    category: str | None = None,
) -> dict[str, float]:
    """Calculate satisfaction score for each member regarding the chosen option.

    Scoring rules:
    - 1.0 if the chosen option is positive for that member
    - 0.5 if neutral or unmentioned for that member
    - 0.0 if negative for that member

    Args:
        records: List of preference records.
        chosen: Chosen winning option name (or None).
        category: Optional category filter ('Destination' or 'Activity').

    Returns:
        dict mapping member name to float satisfaction score [0.0, 1.0].
    """
    if not records:
        return {}

    # Find all unique members in input records
    all_members: set[str] = set()
    for raw in records:
        if isinstance(raw, PreferenceRecord):
            all_members.add(raw.member)
        else:
            all_members.add(raw.get("member") if isinstance(raw, dict) else raw.member)

    if not all_members:
        return {}

    if chosen is None:
        return {m: 0.5 for m in sorted(all_members)}

    canon_chosen = normalize_name(chosen, category=category)
    member_stances = _deduplicate_records(records, category=category)

    satisfaction: dict[str, float] = {}
    for m in sorted(all_members):
        stances = member_stances.get(m, {})
        stance = stances.get(canon_chosen)
        if stance == "positive":
            satisfaction[m] = 1.0
        elif stance == "negative":
            satisfaction[m] = 0.0
        else:
            # Neutral or unmentioned
            satisfaction[m] = 0.5

    return satisfaction


def min_member_satisfaction(
    records: list[Any],
    chosen: str | None,
    category: str | None = None,
) -> float:
    """Return the minimum member satisfaction across all group members.

    Args:
        records: List of preference records.
        chosen: Chosen winning option name (or None).
        category: Optional category filter.

    Returns:
        Minimum satisfaction score (0.0 if no members).
    """
    sat = member_satisfaction(records, chosen, category=category)
    if not sat:
        return 0.0
    return min(sat.values())


def preference_coverage(
    records: list[Any],
    chosen: str | None,
    category: str | None = None,
) -> float:
    """Calculate fraction of members who have at least one positive option equal to chosen option.

    Args:
        records: List of preference records.
        chosen: Chosen winning option name (or None).
        category: Optional category filter.

    Returns:
        Fraction in [0.0, 1.0].
    """
    if not records or chosen is None:
        return 0.0

    all_members: set[str] = set()
    for raw in records:
        if isinstance(raw, PreferenceRecord):
            all_members.add(raw.member)
        else:
            all_members.add(raw.get("member") if isinstance(raw, dict) else raw.member)

    if not all_members:
        return 0.0

    canon_chosen = normalize_name(chosen, category=category)
    member_stances = _deduplicate_records(records, category=category)

    positive_supporters = 0
    for m in all_members:
        stances = member_stances.get(m, {})
        if stances.get(canon_chosen) == "positive":
            positive_supporters += 1

    return round(positive_supporters / len(all_members), 4)
