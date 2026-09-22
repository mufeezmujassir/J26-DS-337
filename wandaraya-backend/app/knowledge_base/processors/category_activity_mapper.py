from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.attraction import Attraction
from app.models.attraction_categories import AttractionCategory
from app.models.attraction_activities import AttractionActivity


@dataclass
class CategoryMatch:
    name:str
    confidence:float
    is_primary:bool=False

    @property
    def score(self) -> float:
        return self.confidence

@dataclass
class ActivityMatch:
    name:str
    suitability_score:float

@dataclass
class MappingResult:
    categories:list[CategoryMatch]=field(default_factory=list)
    activities:list[ActivityMatch]=field(default_factory=list)

class CategoryActivityMapper:
    CATEGORY_RULES = {

        "Nature & Landscapes": {
            "natural_feature",
            "national_park",
            "park",
            "mountain_peak",
        },

        "Beaches & Coastal": {
            "beach",
        },

        "Wildlife & Safari": {
            "wildlife_park",
            "zoo",
        },

        "Culture & Heritage": {
            "cultural_landmark",
            "historical_landmark",
            "monument",
        },

        "History & Archaeology": {
            "historical_landmark",
            "historical_place",
            "archaeological_site",
            "museum",
        },

        "Religious & Spiritual": {
            "hindu_temple",
            "buddhist_temple",
            "church",
            "mosque",
            "place_of_worship",
        },

        "Adventure & Outdoor": {
            "hiking_area",
            "adventure_sports_center",
        },

        "Water & Marine Activities": {
            "marina",
            "beach",
        },

        "Wellness & Ayurveda": {
            "spa",
            "wellness_center",
        },

        "Tea, Agriculture & Plantation": {
            "farm",
        },

        "Food & Culinary": {
            "restaurant",
            "cafe",
            "bakery",
        },

        "Shopping & Local Markets": {
            "market",
            "shopping_mall",
            "store",
        },

        "Entertainment & Nightlife": {
            "night_club",
            "bar",
        },

        "Festivals & Events": {
            "event_venue",
        },

        "Family & Recreation": {
            "amusement_park",
            "aquarium",
            "zoo",
            "park",
        },

        "Urban & City Attractions": {
            "tourist_attraction",
            "plaza",
            "landmark",
        },

        "Photography & Scenic Spots": {
            "scenic_spot",
            "observation_deck",
            "historical_landmark",
        },

        "Educational & Learning": {
            "museum",
            "science_museum",
        },
    }
    ACTIVITY_RULES = {

    "Hiking": {
        "hiking",
        "hiking trail",
        "mountain trail",
    },

    "Trekking": {
        "trekking",
        "long distance trail",
    },

    "Sightseeing": {
        "sightseeing",
        "tourist attraction",
        "landmark",
        "monument",
        "fort",
    },

    "Photography": {
        "photography",
        "photograph",
        "scenic",
        "viewpoint",
        "panoramic",
    },

    "Wildlife Safari": {
        "wildlife safari",
        "safari",
        "national park",
    },

    "Bird Watching": {
        "bird watching",
        "birdwatching",
        "bird species",
    },

    "Whale Watching": {
        "whale watching",
        "whales",
    },

    "Dolphin Watching": {
        "dolphin watching",
        "dolphins",
    },

    "Surfing": {
        "surfing",
        "surf spot",
        "surf beach",
    },

    "Swimming": {
        "swimming",
        "swimmable",
    },

    "Snorkeling": {
        "snorkeling",
        "snorkelling",
    },

    "Scuba Diving": {
        "scuba diving",
        "diving site",
    },

    "Boating": {
        "boating",
        "boat ride",
        "boat tour",
    },

    "Kayaking": {
        "kayaking",
        "kayak",
    },

    "River Rafting": {
        "river rafting",
        "white water rafting",
        "white-water rafting",
    },

    "Camping": {
        "camping",
        "campsite",
    },

    "Rock Climbing": {
        "rock climbing",
        "climbing",
    },

    "Caving": {
        "caving",
        "cave exploration",
    },

    "Cycling": {
        "cycling",
        "bicycle",
        "bike ride",
    },

    "Beach Relaxation": {
        "beach relaxation",
        "relaxing at the beach",
        "sandy beach",
    },

    "Tea Tasting": {
        "tea tasting",
        "taste tea",
    },

    "Tea Factory Visit": {
        "tea factory",
        "tea production",
    },

    "Plantation Tour": {
        "plantation tour",
        "tea estate",
        "spice plantation",
    },

    "Agricultural Experience": {
        "agricultural experience",
        "agriculture",
        "farming",
        "farm visit",
    },

    "Ayurvedic Treatment": {
        "ayurvedic treatment",
        "ayurveda",
    },

    "Meditation": {
        "meditation",
        "mindfulness",
    },

    "Yoga": {
        "yoga",
    },

    "Spa and Wellness": {
        "spa",
        "wellness",
    },

    "Temple Visit": {
        "temple visit",
        "buddhist temple",
        "hindu temple",
    },

    "Cultural Experience": {
        "cultural experience",
        "local culture",
        "tradition",
        "traditional culture",
    },

    "Historical Exploration": {
        "historical",
        "history",
        "archaeological",
        "fort",
        "ancient",
    },

    "Museum Visit": {
        "museum visit",
        "museum",
    },

    "Heritage Exploration": {
        "heritage",
        "world heritage",
        "unesco",
        "architectural heritage",
        "cultural heritage",
    },

    "Local Food Experience": {
        "local food",
        "local cuisine",
        "traditional food",
    },

    "Cooking Class": {
        "cooking class",
        "cooking lesson",
    },

    "Food Tasting": {
        "food tasting",
        "tasting local food",
    },

    "Shopping": {
        "shopping",
        "souvenir",
    },

    "Handicraft Experience": {
        "handicraft",
        "traditional craft",
    },

    "Local Market Visit": {
        "local market",
        "traditional market",
    },

    "Nightlife": {
        "nightlife",
        "night club",
    },

    "Family Recreation": {
        "family recreation",
        "family friendly",
        "family-friendly",
    },

    "Waterfall Visit": {
        "waterfall",
    },

    "Scenic Viewpoint": {
        "scenic viewpoint",
        "viewpoint",
        "panoramic view",
    },

    "Sunrise Viewing": {
        "sunrise",
    },

    "Sunset Viewing": {
        "sunset",
    },

    "Stargazing": {
        "stargazing",
        "night sky",
    },

    "Festival Participation": {
        "festival",
        "religious festival",
        "cultural festival",
    },

    "Event Participation": {
        "event participation",
        "cultural event",
        "tourism event",
    },

    "Educational Visit": {
        "educational visit",
        "educational",
        "learning experience",
    },

    "Train Journey": {
        "train journey",
        "railway journey",
        "scenic train",
    },
    }

    @classmethod
    def map(
        cls,
        attraction: dict[str, Any],
        primary_text: str = "",
        supporting_text: str = "",
    ) -> MappingResult:
        google_types = set(
            attraction
            .get("source_metadata", {})
            .get("types", [])
        )

        name = (
            attraction.get("name")
            or ""
        )

        strong_text = " ".join(
            [
                name,
                primary_text,
                " ".join(google_types),
            ]
        ).casefold()

        weak_text = (
            supporting_text
            or ""
        ).casefold()

        categories = cls._map_categories(
            google_types=google_types,
            strong_text=strong_text,
            weak_text=weak_text,
        )

        activities = cls._map_activities(
            strong_text=strong_text,
            weak_text=weak_text,
        )

        return MappingResult(
            categories=categories,
            activities=activities,
        )

    @classmethod
    def _map_categories(
        cls,
        google_types: set[str],
        strong_text: str,
        weak_text: str,
    ) -> list[CategoryMatch]:

        matches: list[CategoryMatch] = []

        for category, rules in cls.CATEGORY_RULES.items():

            score = 0.0
            strong_evidence = False

            for rule in rules:

                readable_rule = (
                    rule.replace("_", " ")
                )

                # Google type = strongest evidence
                if rule in google_types:
                    score += 0.60
                    strong_evidence = True

                # Name/Wikipedia evidence
                if readable_rule in strong_text:
                    score += 0.25
                    strong_evidence = True

                # Wikivoyage = supporting evidence only
                if readable_rule in weak_text:
                    score += 0.10

            score = min(
                score,
                1.0,
            )

            # Critical:
            # supporting Wikivoyage text alone
            # cannot create a category.
            if (
                strong_evidence
                and score >= 0.50
            ):
                matches.append(
                    CategoryMatch(
                        name=category,
                        confidence=score,
                    )
                )

        matches.sort(
            key=lambda item: item.confidence,
            reverse=True,
        )

        if matches:
            matches[0].is_primary = True

        return matches

    @classmethod
    def _map_activities(
        cls,
        strong_text: str,
        weak_text: str,
    ) -> list[ActivityMatch]:

        matches: list[ActivityMatch] = []

        for activity, keywords in cls.ACTIVITY_RULES.items():

            strong_matches = 0
            weak_matches = 0

            for keyword in keywords:

                if keyword in strong_text:
                    strong_matches += 1

                if keyword in weak_text:
                    weak_matches += 1

            # Do not create an activity from
            # Wikivoyage evidence alone.
            if strong_matches == 0:
                continue

            score = (
                0.50
                + (strong_matches * 0.10)
                + (weak_matches * 0.03)
            )

            score = min(
                score,
                1.0,
            )

            matches.append(
                ActivityMatch(
                    name=activity,
                    suitability_score=score,
                )
            )

        matches.sort(
            key=lambda item: item.suitability_score,
            reverse=True,
        )

        return matches

        return matches