"""Simulate multi-turn conversations and PPE-module outputs.

Each conversation records the constraints (vibe, budget, must-see, pace),
confirmations and rejections that the live Progressive Preference
Elicitation (PPE) module would extract turn by turn, plus an initial plan
built from real Sri Lankan attractions.
"""

from __future__ import annotations

import hashlib
import logging
import random
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.classifiers import (
    PERSONA_CATEGORIES,
    PERSONAS,
    PERSONA_VIBE,
    RAW_ATTRACTIONS_FILENAME,
    load_jsonl,
)
from app.replanning.dynamic_replanning.classifiers.consistency import (
    ACTIVITY_BUFFER_MINUTES,
    ACTIVITY_BUFFER_RELAXED_MINUTES,
    ACTIVITIES_PER_DAY_RANGE,
    ACTIVITY_COST_RANGE_USD,
    HOTEL_COST_PER_NIGHT_USD,
    PACES,
    PLAN_DAILY_BUDGET_USD,
    TRANSPORT_COST_PER_DAY_USD,
    TRIP_DAYS,
    VIBES,
    DEFAULT_SEED,
)

LOGGER = logging.getLogger(__name__)

START_TIMES_MINUTES = (480, 540, 600)  # 08:00, 09:00, 10:00


def _stable_rng(*parts: Any, seed: int = DEFAULT_SEED) -> random.Random:
    """Return a deterministic RNG derived from ``seed`` and ``parts``."""

    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()
    return random.Random(int(digest, 16) % (2**31))


def _activity_cost(rng: random.Random) -> float:
    low, high = ACTIVITY_COST_RANGE_USD
    return round(rng.uniform(low, high), 2)


class ConversationGenerator:
    """Generate multi-turn travel conversations backed by real attractions."""

    def __init__(self, attractions_path: str, seed: int = DEFAULT_SEED) -> None:
        self.attractions_path = attractions_path
        self.seed = seed
        self.attractions: List[Dict[str, Any]] = []
        self._by_category: Dict[str, List[Dict[str, Any]]] = {}
        self._districts: List[str] = []

    def load_attractions(self) -> List[Dict[str, Any]]:
        """Load and index the real attraction catalogue."""

        self.attractions = load_jsonl(self.attractions_path)
        if not self.attractions:
            raise ValueError(f"No attractions loaded from {self.attractions_path}")

        self._by_category = {}
        for attraction in self.attractions:
            self._by_category.setdefault(attraction["category"], []).append(attraction)

        self._districts = sorted({a["district"] for a in self.attractions})
        LOGGER.info(
            "Loaded %d attractions across %d districts and %d categories",
            len(self.attractions),
            len(self._districts),
            len(self._by_category),
        )
        return self.attractions

    def generate_conversation(
        self,
        persona: str,
        start_city: str,
        num_turns: int,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """Generate one conversation with PPE-style extracted state."""

        rng = rng or random.Random(self.seed)
        categories = PERSONA_CATEGORIES.get(persona, tuple(self._by_category))
        vibe = PERSONA_VIBE.get(persona, rng.choice(VIBES))
        pace = rng.choice(PACES)
        daily_budget = PLAN_DAILY_BUDGET_USD.get(persona, 80.0)
        persona_budget = round(daily_budget * TRIP_DAYS, 2)
        no_rushing = pace == "slow"

        # Build the plan first, then set the stated budget slightly above the
        # plan cost so the initial plan is always within budget.
        initial_plan = self._build_plan(
            rng, persona, start_city, vibe, persona_budget, no_rushing
        )
        budget_usd = round(
            max(persona_budget, initial_plan["total_cost_usd"])
            * rng.uniform(1.08, 1.30),
            2,
        )
        initial_plan["budget_usd"] = budget_usd
        plan_names = [a["name"] for a in initial_plan["activities"]]

        turns: List[Dict[str, Any]] = []
        constraints: Dict[str, Any] = {
            "vibe": vibe,
            "budget_usd": budget_usd,
            "pace": pace,
            "must_see": [],
            "no_rushing": no_rushing,
        }
        confirmations: List[str] = []
        rejections: List[str] = []

        for turn_number in range(1, num_turns + 1):
            stated: Dict[str, Any] = {}
            if turn_number == 1:
                stated["vibe"] = vibe
                stated["budget_usd"] = budget_usd
            elif turn_number == 2 and rng.random() < 0.6:
                stated["pace"] = pace
            elif turn_number == 3 and rng.random() < 0.5:
                candidates = [
                    n
                    for n in plan_names
                    if n not in constraints["must_see"]
                    and n not in rejections
                ]
                if candidates:
                    candidate = rng.choice(candidates)
                    constraints["must_see"].append(candidate)
                    stated["must_see"] = candidate

            confirmed: List[str] = []
            rejected: List[str] = []
            available = [
                n
                for n in plan_names
                if n not in rejections and n not in constraints["must_see"]
            ]
            if available and rng.random() < 0.7:
                pick = rng.choice(available)
                if rng.random() < 0.75:
                    confirmed.append(pick)
                    if pick not in confirmations:
                        confirmations.append(pick)
                else:
                    rejected.append(pick)
                    if pick not in rejections:
                        rejections.append(pick)

            turns.append(
                {
                    "turn_number": turn_number,
                    "user_message": self._user_message(
                        persona, stated, confirmed, rejected
                    ),
                    "constraints_stated": stated,
                    "confirmations": confirmed,
                    "rejections": rejected,
                }
            )

        return {
            "conversation_id": f"conv_{rng.randint(0, 10**9):08d}",
            "persona": persona,
            "start_city": start_city,
            "num_turns": num_turns,
            "turns": turns,
            "constraints": constraints,
            "confirmations": confirmations,
            "rejections": rejections,
            "initial_plan": initial_plan,
        }

    def generate_batch(self, n: int) -> List[Dict[str, Any]]:
        """Generate ``n`` conversations deterministically from the seed."""

        if not self.attractions:
            self.load_attractions()

        rng = random.Random(self.seed)
        conversations: List[Dict[str, Any]] = []
        for index in range(n):
            persona = rng.choice(PERSONAS)
            start_city = rng.choice(self._districts)
            num_turns = rng.randint(3, 6)
            conversations.append(
                self.generate_conversation(
                    persona, start_city, num_turns, rng=rng
                )
            )
        LOGGER.info("Generated %d conversations", len(conversations))
        return conversations

    def build_plan(
        self,
        rng: random.Random,
        persona: str,
        start_city: str,
        vibe: str,
        budget_usd: float,
        no_rushing: bool,
    ) -> Dict[str, Any]:
        """Public wrapper around :meth:`_build_plan`."""

        return self._build_plan(
            rng, persona, start_city, vibe, budget_usd, no_rushing
        )

    def pick_attraction(
        self,
        rng: random.Random,
        persona: str,
        exclude: set,
    ) -> Optional[Dict[str, Any]]:
        """Pick a persona-preferred attraction not in ``exclude``."""

        categories = PERSONA_CATEGORIES.get(persona, tuple(self._by_category))
        pool: List[Dict[str, Any]] = []
        for category in categories:
            pool.extend(
                a
                for a in self._by_category.get(category, [])
                if a["name"] not in exclude
            )
        if not pool:
            pool = [
                a for a in self.attractions if a["name"] not in exclude
            ]
        if not pool:
            return None
        return rng.choice(pool)

    def _build_plan(
        self,
        rng: random.Random,
        persona: str,
        start_city: str,
        vibe: str,
        budget_usd: float,
        no_rushing: bool,
    ) -> Dict[str, Any]:
        """Build an initial plan of 2-4 real activities per day."""

        categories = PERSONA_CATEGORIES.get(persona, tuple(self._by_category))
        buffer_minutes = (
            ACTIVITY_BUFFER_RELAXED_MINUTES
            if no_rushing
            else ACTIVITY_BUFFER_MINUTES
        )

        activities: List[Dict[str, Any]] = []
        used: set = set()
        for day in range(1, TRIP_DAYS + 1):
            num_activities = rng.randint(*ACTIVITIES_PER_DAY_RANGE)
            start_minutes = rng.choice(START_TIMES_MINUTES)
            for _ in range(num_activities):
                attraction = self._pick_for_day(
                    rng, categories, start_city, used
                )
                if attraction is None:
                    break
                used.add(attraction["name"])
                duration = int(attraction.get("duration_minutes") or 120)
                activities.append(
                    {
                        "attraction_id": attraction["attraction_id"],
                        "name": attraction["name"],
                        "district": attraction["district"],
                        "category": attraction["category"],
                        "day": day,
                        "start_minutes": start_minutes,
                        "duration_minutes": duration,
                        "entry_fee_usd": float(attraction.get("entry_fee_usd", 0.0)),
                        "activity_cost_usd": _activity_cost(rng),
                    }
                )
                start_minutes += duration + buffer_minutes

        fixed_daily = HOTEL_COST_PER_NIGHT_USD + TRANSPORT_COST_PER_DAY_USD
        total_cost = round(
            fixed_daily * TRIP_DAYS
            + sum(a["activity_cost_usd"] for a in activities),
            2,
        )

        return {
            "plan_id": f"plan_{rng.randint(0, 10**9):08d}",
            "vibe": vibe,
            "total_cost_usd": total_cost,
            "budget_usd": budget_usd,
            "activities": activities,
        }

    def _pick_for_day(
        self,
        rng: random.Random,
        categories: tuple,
        start_city: str,
        used: set,
    ) -> Optional[Dict[str, Any]]:
        """Prefer same-district, then persona-category attractions."""

        candidates = [
            a
            for a in self.attractions
            if a["name"] not in used and a["district"] == start_city
        ]
        if candidates:
            return rng.choice(candidates)

        pool: List[Dict[str, Any]] = []
        for category in categories:
            pool.extend(
                a for a in self._by_category.get(category, []) if a["name"] not in used
            )
        if not pool:
            pool = [a for a in self.attractions if a["name"] not in used]
        if not pool:
            return None
        return rng.choice(pool)

    @staticmethod
    def _user_message(
        persona: str,
        stated: Dict[str, Any],
        confirmed: List[str],
        rejected: List[str],
    ) -> str:
        parts: List[str] = []
        if "vibe" in stated:
            parts.append(f"I want a {stated['vibe']} trip")
        if "budget_usd" in stated:
            parts.append(f"budget around ${stated['budget_usd']:.0f} total")
        if "pace" in stated:
            parts.append(f"a {stated['pace']} pace please")
        if "must_see" in stated:
            parts.append(f"make sure to include {stated['must_see']}")
        if confirmed:
            parts.append(f"yes, keep {confirmed[0]}")
        if rejected:
            parts.append(f"actually drop {rejected[0]}")
        if not parts:
            parts.append(f"({persona} traveller continues planning)")
        return "; ".join(parts) + "."


__all__ = ["ConversationGenerator"]
