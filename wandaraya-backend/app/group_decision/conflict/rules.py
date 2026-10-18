"""Rule-based Conflict Detector for Step 9 (WANDARAYA Component 3).

Detects Destination, Activity, Budget, and Schedule conflicts based on
deterministic rules and configurable thresholds without ML or emotion signals.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from app.group_decision.conflict.normalize import load_conflict_config, normalize_name
from app.group_decision.conflict.schemas import (
    CONFLICT_CATEGORIES,
    PreferenceRecord,
)

logger = logging.getLogger(__name__)


def _extract_dedup_key(rec: PreferenceRecord, config: dict[str, Any]) -> tuple[str, Any]:
    """Generate (category, name) deduplication key per member.

    Ignores a member's own contradictory records: only latest is kept.
    """
    cat = rec.category
    val = rec.value

    if cat == "Destination":
        dest_name = normalize_name(val.name, category="Destination", config=config)
        return ("Destination", dest_name)
    if cat == "Activity":
        act_name = normalize_name(val.name, category="Activity", config=config)
        return ("Activity", act_name)
    if cat == "Budget":
        # Keep latest record per scope (per_person or total)
        return ("Budget", val.scope)
    if cat == "Schedule":
        # Keep latest schedule record
        return ("Schedule", "default")
    # For ignored categories (Food, Accommodation, etc.)
    name_attr = getattr(val, "name", None) or (val.get("name") if isinstance(val, dict) else "")
    return (cat, name_attr)


def detect_conflicts(
    records: list[Any],
    config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Detect conflicts among group member preference records.

    Rules applied:
    1. Destination, HARD: one member positive, another negative about same destination.
    2. Destination, SOFT: members positive about different destinations and no member
       is positive about both.
    3. Activity, HARD: one member positive, another negative about same activity.
    4. Budget: ranges do not overlap or overlap < min_overlap_fraction (default 0.3).
       Compares only records with same scope and currency, treating missing bounds as infinity.
       Severity is HARD if gap ratio > hard_gap_ratio, else SOFT.
    5. Schedule: date ranges overlap < min_overlap_days (default 2), or time_of_day values
       differ for same date. Records with no dates are skipped.

    Args:
        records: List of structured preference records (dicts or PreferenceRecord objects).
        config_path: Optional path to conflict_rules.yaml.
        config: Optional pre-loaded configuration dictionary.

    Returns:
        Deterministic list of conflict dicts.
    """
    if not records:
        return []

    # 1. Load configuration and thresholds
    cfg = config or load_conflict_config(config_path)
    budget_cfg = cfg.get("budget", {})
    schedule_cfg = cfg.get("schedule", {})

    min_overlap_fraction = float(budget_cfg.get("min_overlap_fraction", 0.3))
    hard_gap_ratio = float(budget_cfg.get("hard_gap_ratio", 0.25))
    min_overlap_days = int(schedule_cfg.get("min_overlap_days", 2))

    # 2. Validate all records with Pydantic schemas
    validated_records: list[PreferenceRecord] = []
    for raw in records:
        if isinstance(raw, PreferenceRecord):
            validated_records.append(raw)
        else:
            validated_records.append(PreferenceRecord.model_validate(raw))

    # 3. Deduplicate / resolve self-contradictions: keep only latest per (member, category, name)
    deduped_map: dict[tuple[str, str, Any], PreferenceRecord] = {}
    for rec in validated_records:
        key = _extract_dedup_key(rec, cfg)
        full_key = (rec.member, key[0], key[1])
        if full_key in deduped_map:
            logger.warning(
                "Member '%s' has contradictory/multiple records for %s %s; using latest record.",
                rec.member,
                key[0],
                key[1],
            )
        deduped_map[full_key] = rec

    active_records = list(deduped_map.values())

    # 4. Check unique members count across entire active group
    unique_members = {r.member for r in active_records}
    if len(unique_members) <= 1:
        return []

    conflicts: list[dict[str, Any]] = []

    # -------------------------------------------------------------
    # Rule 1 & Rule 2: Destination Conflicts
    # -------------------------------------------------------------
    dest_records = [r for r in active_records if r.category == "Destination"]
    if dest_records:
        # Group stances by canonical destination
        dest_stances: dict[str, dict[str, set[str]]] = {}
        # Track all positive destinations per member
        member_pos_dests: dict[str, set[str]] = {m: set() for m in unique_members}

        for r in dest_records:
            canon_dest = normalize_name(r.value.name, category="Destination", config=cfg)
            if canon_dest not in dest_stances:
                dest_stances[canon_dest] = {"positive": set(), "negative": set(), "neutral": set()}
            dest_stances[canon_dest][r.stance].add(r.member)
            if r.stance == "positive":
                member_pos_dests[r.member].add(canon_dest)

        # Rule 1: Destination HARD - positive vs negative on same destination
        for canon_dest, stances in sorted(dest_stances.items()):
            pos_members = sorted(stances["positive"])
            neg_members = sorted(stances["negative"])
            if pos_members and neg_members:
                involved = sorted(set(pos_members).union(neg_members))
                conflicts.append({
                    "type": "Destination",
                    "severity": "hard",
                    "rule_id": "DEST_HARD",
                    "members": involved,
                    "items": {
                        "destination": canon_dest,
                        "positive_members": pos_members,
                        "negative_members": neg_members,
                    },
                    "explanation": (
                        f"Hard destination conflict on '{canon_dest}': "
                        f"supported by {pos_members}, opposed by {neg_members}."
                    ),
                    "features": {
                        "number_of_members_involved": len(involved),
                        "number_of_supporters": len(pos_members),
                        "number_of_opponents": len(neg_members),
                        "overlap_ratio": 0.0,
                        "gap_size": 0.0,
                    },
                })

        # Rule 2: Destination SOFT - positive on different destinations, no member positive about both
        pos_dest_keys = sorted(
            [d for d, s in dest_stances.items() if len(s["positive"]) > 0]
        )
        for i in range(len(pos_dest_keys)):
            for j in range(i + 1, len(pos_dest_keys)):
                d1 = pos_dest_keys[i]
                d2 = pos_dest_keys[j]
                sup1 = dest_stances[d1]["positive"]
                sup2 = dest_stances[d2]["positive"]

                # Check if any member likes both
                members_both = sup1.intersection(sup2)
                if not members_both:
                    # Soft conflict between d1 and d2
                    involved = sorted(sup1.union(sup2))
                    s1_list = sorted(sup1)
                    s2_list = sorted(sup2)
                    conflicts.append({
                        "type": "Destination",
                        "severity": "soft",
                        "rule_id": "DEST_SOFT",
                        "members": involved,
                        "items": {
                            "destinations": [d1, d2],
                            "supporters_by_destination": {
                                d1: s1_list,
                                d2: s2_list,
                            },
                        },
                        "explanation": (
                            f"Soft destination conflict: {s1_list} prefer '{d1}' while "
                            f"{s2_list} prefer '{d2}', and no member supports both."
                        ),
                        "features": {
                            "number_of_members_involved": len(involved),
                            "number_of_supporters": len(involved),
                            "number_of_opponents": 0,
                            "overlap_ratio": 0.0,
                            "gap_size": 0.0,
                        },
                    })

    # -------------------------------------------------------------
    # Rule 3: Activity HARD
    # -------------------------------------------------------------
    act_records = [r for r in active_records if r.category == "Activity"]
    if act_records:
        act_stances: dict[str, dict[str, set[str]]] = {}
        for r in act_records:
            canon_act = normalize_name(r.value.name, category="Activity", config=cfg)
            if canon_act not in act_stances:
                act_stances[canon_act] = {"positive": set(), "negative": set(), "neutral": set()}
            act_stances[canon_act][r.stance].add(r.member)

        for canon_act, stances in sorted(act_stances.items()):
            pos_members = sorted(stances["positive"])
            neg_members = sorted(stances["negative"])
            if pos_members and neg_members:
                involved = sorted(set(pos_members).union(neg_members))
                conflicts.append({
                    "type": "Activity",
                    "severity": "hard",
                    "rule_id": "ACTIVITY_HARD",
                    "members": involved,
                    "items": {
                        "activity": canon_act,
                        "positive_members": pos_members,
                        "negative_members": neg_members,
                    },
                    "explanation": (
                        f"Hard activity conflict on '{canon_act}': "
                        f"supported by {pos_members}, opposed by {neg_members}."
                    ),
                    "features": {
                        "number_of_members_involved": len(involved),
                        "number_of_supporters": len(pos_members),
                        "number_of_opponents": len(neg_members),
                        "overlap_ratio": 0.0,
                        "gap_size": 0.0,
                    },
                })

    # -------------------------------------------------------------
    # Rule 4: Budget Conflicts
    # -------------------------------------------------------------
    budget_records = [r for r in active_records if r.category == "Budget"]
    # Compare each distinct member pair
    for i in range(len(budget_records)):
        for j in range(i + 1, len(budget_records)):
            b1 = budget_records[i]
            b2 = budget_records[j]
            if b1.member == b2.member:
                continue

            v1 = b1.value
            v2 = b2.value

            # Compare only records with the same scope and currency
            if v1.scope != v2.scope or v1.currency != v2.currency:
                continue

            # Skip open-ended ranges by treating missing bound as infinity (min default 0.0, max default inf)
            min1 = v1.min if v1.min is not None else 0.0
            max1 = v1.max if v1.max is not None else float("inf")
            min2 = v2.min if v2.min is not None else 0.0
            max2 = v2.max if v2.max is not None else float("inf")

            len1 = max1 - min1
            len2 = max2 - min2
            smaller_len = min(len1, len2)

            overlap_start = max(min1, min2)
            overlap_end = min(max1, max2)
            overlap = max(0.0, overlap_end - overlap_start)

            # Compute gap if disjoint
            if max1 < min2:
                gap = min2 - max1
            elif max2 < min1:
                gap = min1 - max2
            else:
                gap = 0.0

            # Calculate overlap fraction
            if smaller_len == float("inf"):
                overlap_fraction = 1.0
            elif smaller_len <= 0.0:
                overlap_fraction = 1.0 if (min1 <= max2 and min2 <= max1) else 0.0
            else:
                overlap_fraction = overlap / smaller_len

            # Conflict condition: ranges do not overlap or overlap < fraction of smaller range
            if overlap_fraction < min_overlap_fraction:
                # Severity: HARD if gap ratio > hard_gap_ratio, else SOFT
                if smaller_len != float("inf") and smaller_len > 0:
                    gap_ratio = gap / smaller_len
                else:
                    gap_ratio = 0.0

                severity = "hard" if gap_ratio > hard_gap_ratio else "soft"
                involved = sorted([b1.member, b2.member])

                conflicts.append({
                    "type": "Budget",
                    "severity": severity,
                    "rule_id": "BUDGET_DISCREPANCY",
                    "members": involved,
                    "items": {
                        "currency": v1.currency,
                        "scope": v1.scope,
                        "ranges": {
                            b1.member: [v1.min, v1.max],
                            b2.member: [v2.min, v2.max],
                        },
                        "overlap": round(float(overlap), 2),
                        "gap": round(float(gap), 2),
                    },
                    "explanation": (
                        f"Budget conflict between {b1.member} ([{v1.min}, {v1.max}]) and "
                        f"{b2.member} ([{v2.min}, {v2.max}]) in {v1.currency} ({v1.scope}): "
                        f"overlap fraction {overlap_fraction:.2f} is below threshold {min_overlap_fraction}."
                    ),
                    "features": {
                        "number_of_members_involved": 2,
                        "number_of_supporters": 1,
                        "number_of_opponents": 1,
                        "overlap_ratio": round(float(overlap_fraction), 4),
                        "gap_size": round(float(gap), 2),
                    },
                })

    # -------------------------------------------------------------
    # Rule 5: Schedule Conflicts
    # -------------------------------------------------------------
    sched_records = [r for r in active_records if r.category == "Schedule"]
    # Pairwise comparison
    for i in range(len(sched_records)):
        for j in range(i + 1, len(sched_records)):
            s1 = sched_records[i]
            s2 = sched_records[j]
            if s1.member == s2.member:
                continue

            v1 = s1.value
            v2 = s2.value

            # Records with no dates are skipped
            has_dates_1 = v1.start_date is not None or v1.end_date is not None
            has_dates_2 = v2.start_date is not None or v2.end_date is not None
            if not has_dates_1 or not has_dates_2:
                continue

            start_str1 = v1.start_date or v1.end_date
            end_str1 = v1.end_date or v1.start_date
            start_str2 = v2.start_date or v2.end_date
            end_str2 = v2.end_date or v2.start_date

            d1_start = datetime.strptime(start_str1, "%Y-%m-%d").date()
            d1_end = datetime.strptime(end_str1, "%Y-%m-%d").date()
            d2_start = datetime.strptime(start_str2, "%Y-%m-%d").date()
            d2_end = datetime.strptime(end_str2, "%Y-%m-%d").date()

            overlap_start = max(d1_start, d2_start)
            overlap_end = min(d1_end, d2_end)

            if overlap_end >= overlap_start:
                overlap_days = (overlap_end - overlap_start).days + 1
                gap_days = 0
            else:
                overlap_days = 0
                if d1_end < d2_start:
                    gap_days = (d2_start - d1_end).days
                else:
                    gap_days = (d1_start - d2_end).days

            # Condition 5A: date ranges overlap by fewer than min_overlap_days
            if overlap_days < min_overlap_days:
                severity = "hard" if overlap_days == 0 else "soft"
                involved = sorted([s1.member, s2.member])
                conflicts.append({
                    "type": "Schedule",
                    "severity": severity,
                    "rule_id": "SCHEDULE_DATE_OVERLAP",
                    "members": involved,
                    "items": {
                        "schedules": {
                            s1.member: [start_str1, end_str1],
                            s2.member: [start_str2, end_str2],
                        },
                        "overlap_days": overlap_days,
                        "gap_days": gap_days,
                    },
                    "explanation": (
                        f"Schedule date conflict between {s1.member} and {s2.member}: "
                        f"overlap of {overlap_days} day(s) is less than required {min_overlap_days} day(s)."
                    ),
                    "features": {
                        "number_of_members_involved": 2,
                        "number_of_supporters": 1,
                        "number_of_opponents": 1,
                        "overlap_ratio": float(overlap_days),
                        "gap_size": float(gap_days),
                    },
                })

            # Condition 5B: time_of_day values differ for the same date
            # Applicable when there is at least one common overlapping date
            if overlap_days > 0 and v1.time_of_day and v2.time_of_day:
                if v1.time_of_day != v2.time_of_day:
                    involved = sorted([s1.member, s2.member])
                    conflicts.append({
                        "type": "Schedule",
                        "severity": "soft",
                        "rule_id": "SCHEDULE_TIME_OF_DAY",
                        "members": involved,
                        "items": {
                            "overlap_period": [str(overlap_start), str(overlap_end)],
                            "time_of_day_preferences": {
                                s1.member: v1.time_of_day,
                                s2.member: v2.time_of_day,
                            },
                        },
                        "explanation": (
                            f"Schedule time-of-day conflict between {s1.member} ('{v1.time_of_day}') and "
                            f"{s2.member} ('{v2.time_of_day}') during overlapping dates."
                        ),
                        "features": {
                            "number_of_members_involved": 2,
                            "number_of_supporters": 1,
                            "number_of_opponents": 1,
                            "overlap_ratio": float(overlap_days),
                            "gap_size": 0.0,
                        },
                    })

    # 5. Deterministic sorting
    def _sort_key(c: dict[str, Any]) -> tuple[Any, ...]:
        return (
            c["type"],
            c["severity"],
            c["rule_id"],
            tuple(c["members"]),
            json.dumps(c["items"], sort_keys=True),
        )

    conflicts.sort(key=_sort_key)
    return conflicts
