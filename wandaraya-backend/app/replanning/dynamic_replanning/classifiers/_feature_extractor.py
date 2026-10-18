"""Compute the 14 intent-preservation features from original/revised plans."""

from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List

from app.replanning.dynamic_replanning.classifiers._itinerary_generator import haversine_distance

__all__ = ["extract_features"]


def _get_context_rand(
    original: Dict[str, Any],
    revised: Dict[str, Any],
) -> Dict[str, Any]:
    key = (
        str(original.get("itinerary_id", "o"))
        + "|"
        + str(revised.get("itinerary_id", "r"))
    )
    h = hashlib.sha256(key.encode()).hexdigest()
    sr = random.Random(int(h, 16) % (2**31))
    return {
        "anchor_age_minutes": sr.randint(0, 1440),
        "num_turns_since_anchor": sr.randint(0, 20),
        "num_prior_replans": sr.randint(0, 5),
    }


def _by_slot(acts: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    return {int(a.get("slot", i)): a for i, a in enumerate(acts)}


def extract_features(
    original: Dict[str, Any],
    disruption: Dict[str, Any],
    revised: Dict[str, Any],
) -> Dict[str, Any]:
    ctx = revised.get("context", {}) or {}
    rand = _get_context_rand(original, revised)

    orig_v = original.get("vibe")
    rev_v = revised.get("vibe")
    vibe_match = int(orig_v == rev_v) if orig_v is not None and rev_v is not None else 1

    orig_cost = float(original.get("cost_total", 0.0))
    rev_cost = float(revised.get("cost_total", orig_cost))
    budget_diff_ratio = (rev_cost - orig_cost) / max(orig_cost, 1.0)

    orig_b = set(original.get("confirmed_bookings", []) or [])
    rev_b = set(revised.get("confirmed_bookings", []) or [])
    bookings_preserved_ratio = len(orig_b & rev_b) / max(len(orig_b), 1) if orig_b else 1.0

    orig_m = set(original.get("must_see", []) or [])
    rev_m = set(revised.get("must_see", []) or [])
    must_see_preserved_ratio = len(orig_m & rev_m) / max(len(orig_m), 1) if orig_m else 1.0

    orig_acts = list(original.get("activities", []))
    rev_acts = list(revised.get("activities", []))
    orig_by = _by_slot(orig_acts)
    rev_by = _by_slot(rev_acts)

    all_slots = set(orig_by) | set(rev_by)
    time_shifts = []
    loc_dists = []
    replacements = 0
    removed = 0
    added = 0

    for slot in all_slots:
        o = orig_by.get(slot)
        r = rev_by.get(slot)
        if o is not None and r is not None:
            if int(o.get("attraction_id")) != int(r.get("attraction_id")):
                replacements += 1
                try:
                    d = haversine_distance(
                        float(o.get("lat", 0.0)),
                        float(o.get("lng", 0.0)),
                        float(r.get("lat", 0.0)),
                        float(r.get("lng", 0.0)),
                    )
                    loc_dists.append(d)
                except Exception:
                    pass
            # time shift for matched/replaced pair
            try:
                time_shifts.append(
                    abs(int(o.get("start_minutes", 0)) - int(r.get("start_minutes", 0)))
                )
            except Exception:
                pass
        elif o is not None and r is None:
            removed += 1
        elif o is None and r is not None:
            added += 1

    time_shift_minutes = float(max(time_shifts)) if time_shifts else 0.0
    location_distance_km = float(max(loc_dists)) if loc_dists else 0.0
    activity_count_change = len(rev_by) - len(orig_by)
    num_activities_changed = replacements + removed + added
    ratio_activities_changed = num_activities_changed / max(len(orig_by), 1) if orig_by else 0.0

    features = {
        "vibe_match": int(vibe_match),
        "budget_diff_ratio": float(budget_diff_ratio),
        "bookings_preserved_ratio": float(bookings_preserved_ratio),
        "must_see_preserved_ratio": float(must_see_preserved_ratio),
        "time_shift_minutes": float(time_shift_minutes),
        "activity_count_change": int(activity_count_change),
        "location_distance_km": float(location_distance_km),
        "num_activities_changed": int(num_activities_changed),
        "ratio_activities_changed": float(ratio_activities_changed),
        "anchor_age_minutes": int(ctx.get("anchor_age_minutes", rand["anchor_age_minutes"])),
        "num_turns_since_anchor": int(ctx.get("num_turns_since_anchor", rand["num_turns_since_anchor"])),
        "user_explicitly_changed_vibe": int(ctx.get("user_explicitly_changed_vibe", 0)),
        "user_explicitly_changed_budget": int(ctx.get("user_explicitly_changed_budget", 0)),
        "num_prior_replans": int(ctx.get("num_prior_replans", rand["num_prior_replans"])),
    }
    return features
