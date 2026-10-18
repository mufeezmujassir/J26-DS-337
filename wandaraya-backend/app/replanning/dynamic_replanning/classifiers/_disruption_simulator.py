"""Simulate disruptions and generate revised plans with controlled break types."""

from __future__ import annotations

import copy
import hashlib
import logging
import random
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.classifiers import (
    BROKEN_BUDGET_OVERRUN,
    BROKEN_LOCATION_SHIFT,
    BROKEN_MISSING_BOOKING,
    BROKEN_MISSING_MUST_SEE,
    BROKEN_MULTIPLE_MINOR,
    BROKEN_TIME_SHIFT,
    BROKEN_TYPES,
    BROKEN_VIBE_MISMATCH,
    DEFAULT_ACTIVITY_DURATION_MINUTES,
    VIBES,
)
from app.replanning.dynamic_replanning.classifiers._itinerary_generator import (
    haversine_distance,
)

LOGGER = logging.getLogger(__name__)

__all__ = ["DisruptionSimulator"]


class DisruptionSimulator:
    def __init__(self, seed: int = 42, attractions: Optional[List[Dict[str, Any]]] = None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.attractions = list(attractions) if attractions else []

    def simulate_disruption(self, itinerary: Dict[str, Any]) -> Dict[str, Any]:
        source = self.rng.choice(["weather", "places", "gps", "complaint"])
        acts = list(itinerary.get("activities", [])) or []
        if not acts:
            affected = 0
        else:
            if source == "weather":
                outdoor = [a for a in acts if a.get("is_outdoor")]
                affected = (self.rng.choice(outdoor) if outdoor else self.rng.choice(acts))["slot"]
            else:
                affected = self.rng.choice(acts)["slot"]

        return {
            "disruption_id": f"dis_{self.rng.randint(0, 9999):04d}",
            "source": source,
            "type": source,
            "affected_slot": affected,
            "reason": f"{source} disruption affecting slot {affected}",
        }

    def _find_replacement(
        self,
        category: str,
        exclude_ids: List[int],
        near_lat: Optional[float] = None,
        near_lng: Optional[float] = None,
        min_km: float = 0.0,
        max_km: float = 10000.0,
        prefer_same_category: bool = True,
    ) -> Optional[Dict[str, Any]]:
        exclude_set = set(exclude_ids)
        pool = [
            a
            for a in self.attractions
            if int(a["attraction_id"]) not in exclude_set and a.get("district")
        ]
        if prefer_same_category:
            pool_cat = [a for a in pool if a.get("category") == category]
            if pool_cat:
                pool = pool_cat

        if not pool:
            pool = [
                a
                for a in self.attractions
                if int(a["attraction_id"]) not in exclude_set
            ]
            if not pool:
                return None

        if near_lat is not None and near_lng is not None:
            scored = []
            for a in pool:
                d = haversine_distance(near_lat, near_lng, float(a["lat"]), float(a["lng"]))
                if d < min_km or d > max_km:
                    continue
                scored.append((d, a))
            if scored:
                self.rng.shuffle(scored)
                scored.sort(key=lambda x: (x[0], self.rng.random()))
                return scored[0][1]

        return self.rng.choice(pool)

    def _stable_context(self, key: str, itin_id: str, base_rng: random.Random) -> Dict[str, Any]:
        h = hashlib.sha256(f"{key}|{itin_id}|{self.seed}".encode()).hexdigest()
        sr = random.Random(int(h, 16) % (2**31))
        return {
            "anchor_age_minutes": sr.randint(0, 1440),
            "num_turns_since_anchor": sr.randint(0, 20),
            "num_prior_replans": sr.randint(0, 5),
            "user_explicitly_changed_vibe": 0,
            "user_explicitly_changed_budget": 0,
        }

    def apply_disruption(
        self,
        itinerary: Dict[str, Any],
        disruption: Dict[str, Any],
        break_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        revised = copy.deepcopy(itinerary)
        acts = list(revised.get("activities", []))
        if not acts:
            return revised

        break_eff = break_type
        if break_eff is None and self.rng.random() < 0.20:
            break_eff = self.rng.choice(BROKEN_TYPES)

        context = self._stable_context(
            "ctx", str(revised.get("itinerary_id", "itin")), self.rng
        )
        context["user_explicitly_changed_vibe"] = 0
        context["user_explicitly_changed_budget"] = 0

        orig_acts = list(itinerary.get("activities", []))

        if break_eff is None:
            # preserved: replace 0-2 nearby activities
            num_repl = self.rng.randint(0, 2)
            for _ in range(num_repl):
                idx = self.rng.randint(0, len(acts) - 1)
                a = acts[idx]
                rep = self._find_replacement(
                    a["category"],
                    [x["attraction_id"] for x in acts],
                    near_lat=a["lat"],
                    near_lng=a["lng"],
                    max_km=5.0,
                    prefer_same_category=True,
                )
                if not rep:
                    rep = self._find_replacement(
                        a["category"],
                        [x["attraction_id"] for x in acts],
                        near_lat=a["lat"],
                        near_lng=a["lng"],
                        max_km=5.0,
                        prefer_same_category=False,
                    )
                if not rep:
                    continue
                # enforce small distance for preserved
                dist = haversine_distance(a["lat"], a["lng"], float(rep["lat"]), float(rep["lng"]))
                if dist > 5.0:
                    continue  # skip; keeps this activity unchanged
                acts[idx]["attraction_id"] = rep["attraction_id"]
                acts[idx]["name"] = rep["name"]
                acts[idx]["category"] = rep["category"]
                acts[idx]["lat"] = float(rep["lat"])
                acts[idx]["lng"] = float(rep["lng"])
                acts[idx]["is_outdoor"] = bool(rep.get("is_outdoor", False))
                acts[idx]["cost_usd"] = float(rep.get("entry_fee_usd", 0.0))
                acts[idx]["duration_minutes"] = int(
                    rep.get("duration_minutes", DEFAULT_ACTIVITY_DURATION_MINUTES)
                )
                acts[idx]["end_minutes"] = acts[idx]["start_minutes"] + acts[idx]["duration_minutes"]
                acts[idx]["time_slot"] = f"{acts[idx]['start_minutes']//60:02d}:{acts[idx]['start_minutes']%60:02d}-{acts[idx]['end_minutes']//60:02d}:{acts[idx]['end_minutes']%60:02d}"
                acts[idx]["is_must_see"] = False
            context["user_explicitly_changed_vibe"] = 0
            context["user_explicitly_changed_budget"] = 0
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["context"] = context
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            return revised

        if break_eff == BROKEN_VIBE_MISMATCH:
            context["user_explicitly_changed_vibe"] = 0
            context["user_explicitly_changed_budget"] = self.rng.randint(0, 1)
            orig_v = revised["vibe"]
            choices = [v for v in VIBES if v != orig_v]
            revised["vibe"] = self.rng.choice(choices) if choices else "mixed"
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["context"] = context
            return revised

        if break_eff == BROKEN_BUDGET_OVERRUN:
            context["user_explicitly_changed_budget"] = 0
            context["user_explicitly_changed_vibe"] = self.rng.randint(0, 1)
            mult = self.rng.uniform(1.15, 1.40)
            revised["cost_total"] = round(itinerary["cost_total"] * mult, 2)
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        if break_eff == BROKEN_MISSING_BOOKING:
            context["user_explicitly_changed_budget"] = self.rng.randint(0, 1)
            context["user_explicitly_changed_vibe"] = self.rng.randint(0, 1)
            bks = list(itinerary.get("confirmed_bookings", []))
            if bks:
                bks.pop(self.rng.randint(0, len(bks) - 1))
            revised["confirmed_bookings"] = bks
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        if break_eff == BROKEN_MISSING_MUST_SEE:
            context["user_explicitly_changed_budget"] = self.rng.randint(0, 1)
            context["user_explicitly_changed_vibe"] = self.rng.randint(0, 1)
            musts = list(itinerary.get("must_see", []))
            dropped = None
            if musts:
                dropped = self.rng.choice(musts)
                musts.remove(dropped)
            revised["must_see"] = musts
            # drop a must-see activity if possible
            if dropped:
                new_acts = []
                dropped_count = 0
                for a in acts:
                    if dropped_count == 0 and a.get("name") == dropped:
                        dropped_count += 1
                        continue
                    new_acts.append(dict(a))
                acts = new_acts
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        if break_eff == BROKEN_TIME_SHIFT:
            context["user_explicitly_changed_budget"] = self.rng.randint(0, 1)
            context["user_explicitly_changed_vibe"] = self.rng.randint(0, 1)
            if acts:
                idx = self.rng.randint(0, len(acts) - 1)
                shift = self.rng.randint(61, 120)
                acts[idx]["start_minutes"] = acts[idx]["start_minutes"] + shift
                acts[idx]["end_minutes"] = acts[idx]["start_minutes"] + acts[idx]["duration_minutes"]
                acts[idx]["time_slot"] = f"{acts[idx]['start_minutes']//60:02d}:{acts[idx]['start_minutes']%60:02d}-{acts[idx]['end_minutes']//60:02d}:{acts[idx]['end_minutes']%60:02d}"
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        if break_eff == BROKEN_LOCATION_SHIFT:
            context["user_explicitly_changed_budget"] = self.rng.randint(0, 1)
            context["user_explicitly_changed_vibe"] = self.rng.randint(0, 1)
            if acts:
                candidates_idx = [i for i, a in enumerate(acts) if not a.get("is_must_see")]
                if not candidates_idx:
                    candidates_idx = list(range(len(acts)))
                idx = self.rng.choice(candidates_idx)
                a = acts[idx]
                rep = self._find_replacement(
                    a["category"],
                    [x["attraction_id"] for x in acts],
                    near_lat=a["lat"],
                    near_lng=a["lng"],
                    min_km=5.0,
                    prefer_same_category=False,
                )
                if not rep:
                    rep = self._find_replacement(
                        a["category"],
                        [x["attraction_id"] for x in acts],
                        near_lat=a["lat"],
                        near_lng=a["lng"],
                        min_km=5.0,
                        prefer_same_category=False,
                    )
                if rep:
                    acts[idx]["attraction_id"] = rep["attraction_id"]
                    acts[idx]["name"] = rep["name"]
                    acts[idx]["category"] = rep["category"]
                    acts[idx]["lat"] = float(rep["lat"])
                    acts[idx]["lng"] = float(rep["lng"])
                    acts[idx]["is_outdoor"] = bool(rep.get("is_outdoor", False))
                    acts[idx]["cost_usd"] = float(rep.get("entry_fee_usd", 0.0))
                    acts[idx]["duration_minutes"] = int(
                        rep.get("duration_minutes", DEFAULT_ACTIVITY_DURATION_MINUTES)
                    )
                    acts[idx]["end_minutes"] = acts[idx]["start_minutes"] + acts[idx]["duration_minutes"]
                    acts[idx]["time_slot"] = f"{acts[idx]['start_minutes']//60:02d}:{acts[idx]['start_minutes']%60:02d}-{acts[idx]['end_minutes']//60:02d}:{acts[idx]['end_minutes']%60:02d}"
                    acts[idx]["is_must_see"] = False
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        if break_eff == BROKEN_MULTIPLE_MINOR:
            context["user_explicitly_changed_budget"] = 0
            context["user_explicitly_changed_vibe"] = 0
            changed = 0
            while changed < 3 and len(acts) >= 1:
                idx = self.rng.randint(0, len(acts) - 1)
                a = acts[idx]
                rep = self._find_replacement(
                    a["category"],
                    [x["attraction_id"] for x in acts],
                    near_lat=a["lat"],
                    near_lng=a["lng"],
                    max_km=5.0,
                    prefer_same_category=True,
                )
                if not rep:
                    break
                acts[idx]["attraction_id"] = rep["attraction_id"]
                acts[idx]["name"] = rep["name"]
                acts[idx]["category"] = rep["category"]
                acts[idx]["lat"] = float(rep["lat"])
                acts[idx]["lng"] = float(rep["lng"])
                acts[idx]["is_outdoor"] = bool(rep.get("is_outdoor", False))
                acts[idx]["cost_usd"] = float(rep.get("entry_fee_usd", 0.0))
                # small time shift
                acts[idx]["start_minutes"] = acts[idx]["start_minutes"] + self.rng.randint(5, 30)
                acts[idx]["duration_minutes"] = int(rep.get("duration_minutes", DEFAULT_ACTIVITY_DURATION_MINUTES))
                acts[idx]["end_minutes"] = acts[idx]["start_minutes"] + acts[idx]["duration_minutes"]
                acts[idx]["time_slot"] = f"{acts[idx]['start_minutes']//60:02d}:{acts[idx]['start_minutes']%60:02d}-{acts[idx]['end_minutes']//60:02d}:{acts[idx]['end_minutes']%60:02d}"
                acts[idx]["is_must_see"] = False
                changed += 1
            revised["activities"] = acts
            revised["days"] = _rebuild_days(acts)
            revised["cost_total"] = itinerary["cost_total"]
            revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
            revised["must_see"] = list(itinerary.get("must_see", []))
            revised["vibe"] = itinerary.get("vibe")
            revised["context"] = context
            return revised

        revised["activities"] = acts
        revised["days"] = _rebuild_days(acts)
        revised["cost_total"] = itinerary["cost_total"]
        revised["confirmed_bookings"] = list(itinerary.get("confirmed_bookings", []))
        revised["must_see"] = list(itinerary.get("must_see", []))
        revised["vibe"] = itinerary.get("vibe")
        revised["context"] = context
        return revised


def _rebuild_days(activities_flat: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_day: Dict[int, List[Dict[str, Any]]] = {}
    for a in activities_flat:
        by_day.setdefault(a["day"], []).append(dict(a))
    days: List[Dict[str, Any]] = []
    for d in sorted(by_day):
        acts = sorted(by_day[d], key=lambda x: (x["start_minutes"], x["slot"]))
        days.append({"day": d, "activities": acts})
    return days
