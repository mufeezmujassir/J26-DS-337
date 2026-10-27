from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.recommendation_graph.prompts.intent_extraction import INTENT_SYSTEM_PROMPT
from app.agents.recommendation_graph.schemas.intent import TravelIntent


INJECTION_PATTERNS = (
    "ignore previous", "ignore all previous", "system prompt", "reveal secret",
    "api key", "execute sql", "run python", "change ranking", "disable safety",
)

ACTIVITY_KEYWORDS = {
    "cultur": "cultural sightseeing", "heritage": "cultural sightseeing",
    "religio": "cultural sightseeing", "temple": "cultural sightseeing",
    "church": "cultural sightseeing", "mosque": "cultural sightseeing",
    "shrine": "cultural sightseeing", "scenic": "scenic sightseeing",
    "hiking": "hiking", "trekking": "trekking", "beach": "beach",
    "swimming": "swimming", "wildlife": "wildlife", "safari": "wildlife",
    "waterfall": "waterfall", "nature": "nature sightseeing",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def deterministic_intent(message: str, trusted_now: datetime) -> tuple[TravelIntent, list[str]]:
    clean = " ".join(message.replace("\x00", " ").split())[:2000]
    lower = clean.casefold()
    warnings: list[str] = []
    if any(pattern in lower for pattern in INJECTION_PATTERNS):
        warnings.append("Potential prompt-injection instructions were ignored; only travel fields were extracted.")

    destination = None
    # Prefer explicit trip/itinerary destination phrases. A broad ``visit X``
    # match used to interpret prose such as "suggested visit time" as the
    # destination "time". Collect candidates and reject context-field labels.
    destination_pattern = re.compile(
        r"(?:\bitinerary\s+for|\btrip\s+to|\bnear|\bin|\baround|\bto|\bvisit)\s+"
        r"([A-Za-z][A-Za-z .'-]{1,60}?)(?=\s+(?:today|tomorrow|on|at|this|next|for|during|with|and|we|i|from|morning|afternoon|evening|night)\b|[,.!?]|$)",
        re.IGNORECASE,
    )
    non_destinations = {
        "time", "date", "duration", "weather", "seasonality", "opening hours",
        "the place", "places", "every recommendation",
    }
    for match in destination_pattern.finditer(clean):
        candidate = match.group(1).strip(" .,-")
        if candidate.casefold() not in non_destinations:
            destination = candidate
            break

    local_now = trusted_now.astimezone(ZoneInfo("Asia/Colombo"))
    travel_date = None
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", clean)
    if iso_match:
        try:
            travel_date = datetime.strptime(iso_match.group(1), "%Y-%m-%d").date().isoformat()
        except ValueError:
            travel_date = None
    elif natural_match := re.search(
        r"\b([0-3]?\d)\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(20\d{2})\b",
        clean,
        re.IGNORECASE,
    ):
        try:
            travel_date = datetime.strptime(
                " ".join(natural_match.groups()), "%d %B %Y"
            ).date().isoformat()
        except ValueError:
            travel_date = None
    elif re.search(r"\btomorrow\b", lower):
        travel_date = (local_now.date() + timedelta(days=1)).isoformat()
    elif re.search(r"\btoday\b", lower):
        travel_date = local_now.date().isoformat()

    travel_time = None
    travel_end_time = None
    time_match = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap]\.?m\.?)\b", lower)
    if time_match:
        hour = int(time_match.group(1)) % 12 + (12 if time_match.group(3).startswith("p") else 0)
        travel_time = f"{hour:02d}:{int(time_match.group(2) or 0):02d}"
    elif (match24 := re.search(r"\b([01]\d|2[0-3]):([0-5]\d)\b", lower)):
        travel_time = f"{match24.group(1)}:{match24.group(2)}"

    range_match = re.search(
        r"\bfrom\s+(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap]\.?m\.?)\s+"
        r"to\s+(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap]\.?m\.?)\b",
        lower,
    )
    if range_match:
        start_hour = int(range_match.group(1)) % 12 + (12 if range_match.group(3).startswith("p") else 0)
        end_hour = int(range_match.group(4)) % 12 + (12 if range_match.group(6).startswith("p") else 0)
        travel_time = f"{start_hour:02d}:{int(range_match.group(2) or 0):02d}"
        travel_end_time = f"{end_hour:02d}:{int(range_match.group(5) or 0):02d}"

    period = next((name for name in ("morning", "afternoon", "evening", "night") if re.search(fr"\b{name}\b", lower)), None)
    activities = _unique([value for keyword, value in ACTIVITY_KEYWORDS.items() if keyword in lower])
    interests = _unique([
        value for keyword, value in {
            "cultur": "culture", "heritage": "heritage", "scenic": "scenery",
            "religio": "religious", "temple": "religious", "church": "religious",
            "mosque": "religious", "shrine": "religious",
            "nature": "nature", "beach": "beach", "wildlife": "wildlife",
            "waterfall": "waterfalls", "photograph": "photography",
        }.items() if keyword in lower
    ])
    group_size = None
    group_match = re.search(r"\b(?:we are|group of|for)\s+(\d{1,3})\b", lower)
    if group_match:
        parsed_group_size = int(group_match.group(1))
        group_size = parsed_group_size if 1 <= parsed_group_size <= 100 else None
    elif (word_group := re.search(r"\b(?:we are|group of)\s+(one|two|three|four|five|six|seven|eight|nine|ten)\b", lower)):
        group_size = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                      "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}[word_group.group(1)]
    duration = None
    if duration_match := re.search(r"\b(\d{1,3})[- ]day\b", lower):
        parsed_duration = int(duration_match.group(1))
        duration = parsed_duration if 1 <= parsed_duration <= 365 else None
    constraints: dict[str, Any] = {}
    if any(word in lower for word in ("affordable", "budget", "cheap")):
        constraints["budget_preference"] = "affordable"
    if "wheelchair" in lower or "accessible" in lower:
        constraints["accessibility_preference"] = "accessible"
    if "public transport" in lower:
        constraints["transport_preference"] = "public_transport"

    return TravelIntent(
        query=clean[:500],
        destination_text=destination,
        travel_date=travel_date,
        travel_time=travel_time,
        travel_end_time=travel_end_time,
        approximate_time_period=period,
        requested_activities=activities,
        user_interests=interests,
        group_size=group_size,
        trip_duration_days=duration,
        group_preferences=({"group_size": group_size} if group_size else {}),
        travel_constraints=constraints,
    ), warnings


class IntentExtractionService:
    def __init__(self, llm=None, *, enabled: bool = False):
        self.llm = llm
        self.enabled = enabled

    async def extract(self, message: str, trusted_now: datetime) -> tuple[TravelIntent, list[str]]:
        deterministic, warnings = deterministic_intent(message, trusted_now)
        if not self.enabled or self.llm is None:
            return deterministic, warnings
        try:
            structured = self.llm.with_structured_output(TravelIntent)
            llm_result = await structured.ainvoke([
                SystemMessage(content=INTENT_SYSTEM_PROMPT),
                HumanMessage(content=f"Trusted current datetime: {trusted_now.isoformat()}\nUser message:\n{message}"),
            ])
            if not isinstance(llm_result, TravelIntent):
                llm_result = TravelIntent.model_validate(llm_result)
            merged = llm_result.model_dump()
            for field in ("destination_text", "travel_date", "travel_time", "travel_end_time", "approximate_time_period", "group_size"):
                value = getattr(deterministic, field)
                if value is not None:
                    merged[field] = value
            for field in ("requested_activities", "user_interests"):
                merged[field] = _unique(getattr(deterministic, field) + list(merged.get(field) or []))
            merged["query"] = deterministic.query
            merged["extraction_method"] = "hybrid"
            return TravelIntent.model_validate(merged), warnings
        except Exception as exc:
            warnings.append(f"Structured LLM intent extraction failed; deterministic extraction used ({type(exc).__name__}).")
            return deterministic, warnings
