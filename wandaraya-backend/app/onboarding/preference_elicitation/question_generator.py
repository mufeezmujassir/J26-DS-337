"""Generate targeted questions for missing fields."""

from __future__ import annotations

import logging
from typing import Dict, List

from app.onboarding.preference_elicitation.utils import call_gemini

LOGGER = logging.getLogger(__name__)

FALLBACK_QUESTIONS = {
    "group_type": "Are you traveling solo, as a couple, with friends, or as a family?",
    "trip_type": "What kind of trip is this? (honeymoon, friends trip, family, solo adventure, or cultural pilgrimage)",
    "vibe": "What vibe are you going for? (relaxed, active, adventurous, mixed, or cultural)",
    "budget_per_day": "What is your budget per day in USD?",
    "duration_days": "How many days will your trip be?",
    "dates": "When are you planning to travel? (rough dates are fine)",
    "departure_point": "Where are you departing from?",
}


class QuestionGenerator:
    def generate_question(self, field: str, context: Dict = None) -> str:
        context = context or {}
        try:
            prompt = (
                "Generate a short, natural, conversational question to ask the user "
                f"about the travel preference field '{field}'. "
                "Keep it to one line, under 40 words. "
                f"Context: {context}\n\nReturn only the question text."
            )
            resp = call_gemini(prompt)
            if resp and resp.strip():
                # clean up
                q = resp.strip().strip('"').strip("'")
                if not q.endswith("?") and not q.endswith("."):
                    q = q + "?"
                return q
        except Exception as e:
            LOGGER.warning(f"Gemini question generation failed, using fallback: {e}")
        return FALLBACK_QUESTIONS.get(field) or f"Could you tell me about {field.replace('_', ' ')}?"

    def generate_question_batch(self, fields: List[str], context: Dict = None) -> List[str]:
        questions = []
        for f in fields:
            questions.append(self.generate_question(f, context))
        return questions
