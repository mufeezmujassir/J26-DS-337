"""Main Preference Elicitor orchestrating the PPE flow."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.onboarding.preference_elicitation.field_extractor import MissingFieldExtractor
from app.onboarding.preference_elicitation.models import (
    ElicitationResponse,
    ElicitationState,
    ElicitationTurn,
    PreferenceProfile,
)
from app.onboarding.preference_elicitation.parser import MessageParser
from app.onboarding.preference_elicitation.profile_builder import ProfileBuilder
from app.onboarding.preference_elicitation.question_generator import QuestionGenerator
from app.onboarding.preference_elicitation.state_manager import ElicitationStateManager
from app.onboarding.preference_elicitation.utils import load_config, now_utc

LOGGER = logging.getLogger(__name__)


class PreferenceElicitor:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        elic_cfg = self.config.get("elicitation", {}) if isinstance(self.config, dict) else {}
        self.max_turns = int(elic_cfg.get("max_turns", 5))
        self.parser = MessageParser()
        self.missing_extractor = MissingFieldExtractor(self.config)
        self.question_generator = QuestionGenerator()
        self.profile_builder = ProfileBuilder()
        self.state_manager = ElicitationStateManager(self.config)

    def start(self, user_id: str, initial_message: str) -> ElicitationResponse:
        # parse initial message
        extracted = self.parser.extract_fields(initial_message)
        profile = self.profile_builder.build_profile(user_id, extracted)
        state = self.state_manager.get_state(user_id)
        state.profile = profile
        state.turns_used = 0
        state.max_turns = self.max_turns
        # record turn
        missing = self.missing_extractor.get_missing_fields(profile)
        state.missing_fields = missing
        if missing:
            field = missing[0]
            q = self.question_generator.generate_question(field, {"profile": profile.model_dump()})
            state.last_question = q
            turn = ElicitationTurn(turn_number=1, question=q, user_answer=initial_message, extracted_fields=extracted, timestamp=now_utc())
            self.state_manager.add_turn(user_id, turn)
            state.turns_used = 1
            self.state_manager.save_state(user_id, state)
            return ElicitationResponse(next_question=q, profile=profile, is_complete=False, turns_used=1)
        else:
            state.is_complete = True
            profile.is_complete = True
            self.state_manager.save_state(user_id, state)
            return ElicitationResponse(next_question=None, profile=profile, is_complete=True, turns_used=0)

    def answer(self, user_id: str, user_message: str) -> ElicitationResponse:
        extracted = self.parser.extract_fields(user_message)
        state = self.state_manager.get_state(user_id)
        profile = self.profile_builder.update_profile(state.profile, extracted)
        state.profile = profile
        missing = self.missing_extractor.get_missing_fields(profile)
        state.missing_fields = missing
        turns = self.state_manager.get_turns(user_id)
        turn_number = len(turns) + 1
        if missing and turn_number < self.max_turns:
            field = missing[0]
            q = self.question_generator.generate_question(field, {"profile": profile.model_dump()})
            state.last_question = q
            turn = ElicitationTurn(turn_number=turn_number, question=q, user_answer=user_message, extracted_fields=extracted, timestamp=now_utc())
            self.state_manager.add_turn(user_id, turn)
            state.turns_used = turn_number
            self.state_manager.save_state(user_id, state)
            return ElicitationResponse(next_question=q, profile=profile, is_complete=False, turns_used=turn_number)
        else:
            # complete or max turns reached
            state.is_complete = True
            profile.is_complete = True
            if turn_number >= 1:  # record turn
                q = state.last_question or ""
                turn = ElicitationTurn(turn_number=turn_number, question=q, user_answer=user_message, extracted_fields=extracted, timestamp=now_utc())
                try:
                    self.state_manager.add_turn(user_id, turn)
                except Exception:
                    pass
            state.turns_used = turn_number
            self.state_manager.save_state(user_id, state)
            return ElicitationResponse(next_question=None, profile=profile, is_complete=True, turns_used=turn_number)

    def get_profile(self, user_id: str) -> PreferenceProfile:
        state = self.state_manager.get_state(user_id)
        return state.profile

    def is_complete(self, user_id: str) -> bool:
        state = self.state_manager.get_state(user_id)
        return bool(state.is_complete) or self.missing_extractor.is_profile_complete(state.profile)
