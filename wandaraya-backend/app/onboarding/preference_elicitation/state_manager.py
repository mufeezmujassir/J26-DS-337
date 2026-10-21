"""Elicitation state management with Redis fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pydantic import ValidationError

from app.onboarding.preference_elicitation.models import (
    ElicitationState,
    ElicitationTurn,
    PreferenceProfile,
)
from app.onboarding.preference_elicitation.utils import load_config, now_utc

LOGGER = logging.getLogger(__name__)

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class ElicitationStateManager:
    def __init__(self, config: dict = None):
        self.config = config or load_config()
        state_cfg = self.config.get("state", {}) if isinstance(self.config, dict) else {}
        self.backend = state_cfg.get("backend", "redis")
        self.ttl_hours = int(state_cfg.get("ttl_hours", 24))
        self.redis_url = state_cfg.get("redis_url") or "redis://localhost:6379"
        self._memory: Dict[str, dict] = {}
        self._redis_client = None
        if self.backend == "redis" and redis is not None:
            try:
                self._redis_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
                # test connection
                self._redis_client.ping()
            except Exception as e:
                LOGGER.warning(f"Redis init failed, falling back to memory: {e}")
                self._redis_client = None
                self.backend = "memory"
        else:
            self.backend = "memory"

    def _serialize_state(self, state: ElicitationState) -> str:
        try:
            return state.model_dump_json()
        except Exception:
            # fallback
            data = state.model_dump()
            # convert datetimes
            def conv(o):
                if isinstance(o, datetime):
                    return o.isoformat()
                if isinstance(o, dict):
                    return {k: conv(v) for k, v in o.items()}
                if isinstance(o, list):
                    return [conv(x) for x in o]
                return o

            return json.dumps(conv(data))

    def _deserialize_state(self, s: str, user_id: str) -> Optional[ElicitationState]:
        try:
            data = json.loads(s)
        except Exception:
            return None
        try:
            return ElicitationState(**data)
        except ValidationError:
            # try to reconstruct
            try:
                prof = PreferenceProfile(**data.get("profile", {}))
                return ElicitationState(
                    user_id=data.get("user_id") or user_id,
                    profile=prof,
                    missing_fields=data.get("missing_fields", []) or [],
                    turns_used=int(data.get("turns_used") or 0),
                    max_turns=int(data.get("max_turns") or 5),
                    last_question=data.get("last_question"),
                    is_complete=bool(data.get("is_complete")),
                )
            except Exception:
                return None

    def get_state(self, user_id: str) -> ElicitationState:
        # try redis
        if self._redis_client is not None:
            try:
                val = self._redis_client.get(f"ppe:state:{user_id}")
                if val:
                    st = self._deserialize_state(val, user_id)
                    if st:
                        return st
            except Exception as e:
                LOGGER.warning(f"Redis get failed: {e}")
        # memory
        if user_id in self._memory:
            st = self._deserialize_state(json.dumps(self._memory[user_id]), user_id)
            if st:
                return st
        # create new
        profile = PreferenceProfile(user_id=user_id, created_at=now_utc(), updated_at=now_utc())
        return ElicitationState(user_id=user_id, profile=profile, max_turns=5)

    def save_state(self, user_id: str, state: ElicitationState) -> None:
        ttl = timedelta(hours=self.ttl_hours)
        # redis
        if self._redis_client is not None:
            try:
                self._redis_client.setex(f"ppe:state:{user_id}", ttl, self._serialize_state(state))
                return
            except Exception as e:
                LOGGER.warning(f"Redis save failed: {e}")
        # memory
        try:
            data = json.loads(state.model_dump_json())
            self._memory[user_id] = data
        except Exception:
            # minimal
            self._memory[user_id] = state.model_dump()

    def add_turn(self, user_id: str, turn: ElicitationTurn) -> None:
        state = self.get_state(user_id)
        turns = self.get_turns(user_id)
        turns.append(turn)
        # store turns in redis/memory
        ttl = timedelta(hours=self.ttl_hours)
        turn_key = f"ppe:turns:{user_id}"
        if self._redis_client is not None:
            try:
                self._redis_client.setex(turn_key, ttl, json.dumps([t.model_dump_json() for t in turns]))
            except Exception:
                pass
        else:
            self._memory[f"{turn_key}"] = [t.model_dump() for t in turns]
        state.turns_used = len(turns)
        self.save_state(user_id, state)

    def get_turns(self, user_id: str) -> List[ElicitationTurn]:
        turn_key = f"ppe:turns:{user_id}"
        if self._redis_client is not None:
            try:
                val = self._redis_client.get(turn_key)
                if val:
                    try:
                        arr = json.loads(val)
                        turns: List[ElicitationTurn] = []
                        for a in arr:
                            try:
                                if isinstance(a, str):
                                    turns.append(ElicitationTurn(**json.loads(a)))
                                else:
                                    turns.append(ElicitationTurn(**a))
                            except Exception:
                                continue
                        return turns
                    except Exception:
                        pass
            except Exception:
                pass
        if f"{turn_key}" in self._memory:
            arr = self._memory[f"{turn_key}"]
            turns: List[ElicitationTurn] = []
            for a in arr:
                try:
                    if isinstance(a, dict):
                        turns.append(ElicitationTurn(**a))
                except Exception:
                    continue
            return turns
        return []

    def clear_state(self, user_id: str) -> None:
        if self._redis_client is not None:
            try:
                self._redis_client.delete(f"ppe:state:{user_id}", f"ppe:turns:{user_id}")
                return
            except Exception:
                pass
        self._memory.pop(f"ppe:state:{user_id}", None)
        self._memory.pop(f"ppe:turns:{user_id}", None)
