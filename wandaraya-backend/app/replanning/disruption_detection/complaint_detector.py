"""Group-chat complaint detector for disruption detection."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from app.replanning.disruption_detection.utils import load_config

LOGGER = logging.getLogger(__name__)

#: Extra keyword -> category hints beyond plain complaint scoring.
CATEGORY_KEYWORDS = {
    "weather": frozenset(
        {
            "rain",
            "raining",
            "flood",
            "flooded",
            "hot",
            "cold",
            "storm",
            "windy",
            "sunny",
            "weather",
        }
    ),
    "attraction": frozenset(
        {
            "closed",
            "crowded",
            "boring",
            "skip",
            "cancel",
            "expensive",
            "queue",
            "packed",
        }
    ),
    "transport": frozenset(
        {
            "late",
            "stuck",
            "traffic",
            "delay",
            "missed",
            "bus",
            "train",
            "taxi",
            "tuktuk",
            "tuk",
            "waiting",
        }
    ),
}

#: Score contribution per matched complaint keyword.
SCORE_PER_KEYWORD = 0.2
#: Extra score when a change request phrase is detected.
CHANGE_REQUEST_BONUS = 0.3


class ComplaintDetector:
    """Scores chat messages for complaint signals."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or load_config("config.yaml")
        complaints_config = self.config.get("complaints", {})
        self.keywords: List[str] = complaints_config.get("keywords", [])
        self.change_request_keywords: List[str] = complaints_config.get(
            "change_request_keywords", []
        )

    def monitor(self, message: str = "") -> Dict[str, Any]:
        """Reduce a translated chat message into a complaint signal."""
        if not message:
            return {
                "complaint_score": 0.0,
                "keywords_found": [],
                "category": "other",
                "change_request": False,
            }

        text = message.lower()

        keywords_found = self._keyword_hits(text, self.keywords)
        change_request = bool(
            self._keyword_hits(text, self.change_request_keywords)
        )

        complaint_score = min(
            1.0,
            SCORE_PER_KEYWORD * len(keywords_found)
            + (CHANGE_REQUEST_BONUS if change_request else 0.0),
        )
        category = self._classify_category(text)

        LOGGER.info(
            "Complaint signal: score=%.2f keywords=%r category=%s "
            "change_request=%s",
            complaint_score,
            keywords_found,
            category,
            change_request,
        )

        return {
            "complaint_score": complaint_score,
            "keywords_found": keywords_found,
            "category": category,
            "change_request": change_request,
        }

    def _classify_category(self, text: str) -> str:
        """Pick the category with the most keyword hits; ties fall back."""
        hits = {
            category: sum(
                1 for keyword in words if self._contains_keyword(text, keyword)
            )
            for category, words in CATEGORY_KEYWORDS.items()
        }
        best = max(hits, key=lambda key: (hits[key], key))
        return best if hits[best] > 0 else "other"

    def _keyword_hits(
        self, text: str, keywords: Sequence[str]
    ) -> List[str]:
        """Return keywords present in text (word-boundary for single words)."""
        return [
            keyword
            for keyword in keywords
            if self._contains_keyword(text, keyword)
        ]

    @staticmethod
    def _contains_keyword(text: str, keyword: str) -> bool:
        """Word-boundary match for plain keywords, substring otherwise."""
        if keyword.isalnum():
            return re.search(
                rf"\b{re.escape(keyword)}\b", text
            ) is not None
        return keyword in text