"""State persistence for the Dynamic Replanning module."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    load_config,
    now_utc,
)
from app.schemas.replanning import IntentAnchor, RevisedPlan, TurnRecord

LOGGER = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "replanning:state"
DEFAULT_TTL_HOURS = 24
BACKEND_REDIS = "redis"
BACKEND_POSTGRES = "postgres"
BACKEND_MEMORY = "memory"
BACKEND_DISABLED = "disabled"

REDIS_SOCKET_TIMEOUT = 1.0
POSTGRES_TABLE = "replanning_state"

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_TABLE} (
    user_id VARCHAR(255) PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

UPSERT_SQL = f"""
INSERT INTO {POSTGRES_TABLE} (user_id, payload, updated_at)
VALUES (:user_id, :payload, NOW())
ON CONFLICT (user_id)
DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
"""

SELECT_SQL = f"""
SELECT payload FROM {POSTGRES_TABLE} WHERE user_id = :user_id
"""

DELETE_SQL = f"""
DELETE FROM {POSTGRES_TABLE} WHERE user_id = :user_id
"""


class ReplanningStateManager:
    """Per-user replanning state with Redis, PostgreSQL, and memory tiers."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        redis_url: Optional[str] = None,
        redis_client: Optional[Any] = None,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        ttl_hours: Optional[int] = None,
        backend: Optional[str] = None,
        enable_postgres: bool = True,
    ) -> None:
        """Create the manager and prepare (but do not open) backends."""

        self._config = config or self._safe_load_config()

        state_config = self._config.get("state", {}) or {}

        self._requested_backend = str(
            backend or state_config.get("backend", BACKEND_REDIS)
        ).lower()

        configured_ttl = state_config.get("ttl_hours", DEFAULT_TTL_HOURS)

        self._ttl_seconds = int(
            ttl_hours if ttl_hours is not None else configured_ttl
        ) * 3600

        self._key_prefix = key_prefix
        self._cache: Dict[str, Dict[str, Any]] = {}

        self._redis_url = redis_url or (os.getenv("REDIS_URL") or None)
        self._redis = redis_client
        self._redis_attempted = redis_client is not None
        self._redis_error_logged = False

        self._postgres_engine: Optional[Any] = None
        self._postgres_attempted = False
        self._postgres_disabled = (
            not enable_postgres
            or self._requested_backend == BACKEND_MEMORY
        )

        if self._requested_backend == BACKEND_MEMORY:
            self._redis = None
            self._redis_attempted = True

        LOGGER.info(
            "ReplanningStateManager initialised (requested backend=%s, "
            "redis_configured=%s, postgres_fallback=%s, ttl=%ss)",
            self._requested_backend,
            bool(self._redis_url) or redis_client is not None,
            not self._postgres_disabled,
            self._ttl_seconds,
        )

    # Public API

    def set_intent_anchor(self, user_id: str, anchor: IntentAnchor) -> None:
        """Store the intent anchor for ``user_id`` and persist it."""

        state = self._get_state(user_id)
        state["intent_anchor"] = anchor.model_dump(mode="json")

        self.save_state(user_id)

        LOGGER.info(
            "Intent anchor set for user %s (vibe=%s, budget=%s, "
            "bookings=%d, must_see=%d)",
            user_id,
            anchor.vibe,
            anchor.budget,
            len(anchor.confirmed_bookings),
            len(anchor.must_see),
        )

    def get_intent_anchor(self, user_id: str) -> Optional[IntentAnchor]:
        """Return the stored anchor, or None when none has been set."""

        data = self._get_state(user_id).get("intent_anchor")

        if not data:
            LOGGER.debug("No intent anchor stored for user %s", user_id)
            return None

        return IntentAnchor.model_validate(data)

    def add_turn(self, user_id: str, turn: TurnRecord) -> None:
        """Append a conversation turn and persist the state."""

        state = self._get_state(user_id)
        state.setdefault("turns", []).append(turn.model_dump(mode="json"))

        self.save_state(user_id)

        LOGGER.info(
            "Turn %d recorded for user %s (decision=%s)",
            turn.turn_number,
            user_id,
            turn.decision,
        )

    def get_conversation_context(
        self,
        user_id: str,
    ) -> List[TurnRecord]:
        """Return every stored turn for ``user_id`` in order."""

        raw_turns = self._get_state(user_id).get("turns", []) or []

        return [TurnRecord.model_validate(turn) for turn in raw_turns]

    def update_current_plan(
        self,
        user_id: str,
        plan: RevisedPlan,
    ) -> None:
        """Store the latest revised plan and persist the state."""

        state = self._get_state(user_id)
        state["current_plan"] = plan.model_dump(mode="json")

        self.save_state(user_id)

        LOGGER.info(
            "Current plan updated for user %s (plan_id=%s, severity=%s)",
            user_id,
            plan.plan_id,
            plan.severity,
        )

    def get_current_plan(self, user_id: str) -> Optional[RevisedPlan]:
        """Return the latest revised plan, or None when none is stored."""

        data = self._get_state(user_id).get("current_plan")

        if not data:
            LOGGER.debug("No current plan stored for user %s", user_id)
            return None

        return RevisedPlan.model_validate(data)

    def save_state(self, user_id: str) -> None:
        """Persist the cached state for ``user_id`` to the backends."""

        state = self._cache.get(user_id)

        if state is None:
            state = self._get_state(user_id)

        state["updated_at"] = now_utc().isoformat()
        payload_text = json.dumps(state, ensure_ascii=False)

        if self._write_redis(user_id, payload_text):
            LOGGER.debug("State for user %s saved to Redis", user_id)
            return

        if self._write_postgres(user_id, payload_text):
            LOGGER.debug("State for user %s saved to PostgreSQL", user_id)
            return

        LOGGER.debug(
            "State for user %s kept in memory only (no backend available)",
            user_id,
        )

    def load_state(self, user_id: str) -> None:
        """Load the persisted state for ``user_id`` into the cache."""

        raw = self._load_raw(user_id)

        if raw is None:
            LOGGER.debug(
                "No persisted state found for user %s; starting fresh",
                user_id,
            )
            return

        self._cache[user_id] = raw

        LOGGER.info(
            "State loaded for user %s (anchor=%s, turns=%d, plan=%s)",
            user_id,
            raw.get("intent_anchor") is not None,
            len(raw.get("turns", []) or []),
            raw.get("current_plan") is not None,
        )

    def clear_state(self, user_id: str) -> None:
        """Remove all state for ``user_id`` from cache and backends."""

        self._cache.pop(user_id, None)

        self._delete_redis(user_id)
        self._delete_postgres(user_id)

        LOGGER.info("State cleared for user %s", user_id)

    @property
    def backend(self) -> str:
        """Return the active backend name for diagnostics."""

        if self._requested_backend == BACKEND_MEMORY:
            return BACKEND_MEMORY

        if self._redis is not None:
            return BACKEND_REDIS

        if self._postgres_engine is not None:
            return BACKEND_POSTGRES

        return BACKEND_MEMORY

    def get_stats(self) -> Dict[str, Any]:
        """Return a small diagnostics snapshot."""

        return {
            "requested_backend": self._requested_backend,
            "active_backend": self.backend,
            "ttl_seconds": self._ttl_seconds,
            "key_prefix": self._key_prefix,
            "cached_users": len(self._cache),
            "redis_configured": bool(self._redis_url),
            "redis_connected": self._redis is not None,
            "postgres_fallback_enabled": not self._postgres_disabled,
            "postgres_connected": self._postgres_engine is not None,
        }

    
    # Internal helpers

    @staticmethod
    def _safe_load_config() -> Dict[str, Any]:
        """Load config, falling back to defaults on any failure."""

        try:
            return load_config()
        except (FileNotFoundError, ValueError) as error:
            LOGGER.warning(
                "Could not load replanning config (%s), using defaults",
                error,
            )
            return DEFAULT_CONFIG

    def _get_state(self, user_id: str) -> Dict[str, Any]:
        """Return the live state for ``user_id``, loading it if needed."""

        if user_id in self._cache:
            return self._cache[user_id]

        raw = self._load_raw(user_id) or self._empty_state(user_id)
        self._cache[user_id] = raw

        return raw

    @staticmethod
    def _empty_state(user_id: str) -> Dict[str, Any]:
        """Return a fresh, empty state scaffold for ``user_id``."""

        return {
            "user_id": user_id,
            "intent_anchor": None,
            "current_plan": None,
            "turns": [],
        }

    def _load_raw(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read raw state from Redis, then PostgreSQL, then nothing."""

        raw = self._read_redis(user_id)

        if raw is not None:
            return raw

        return self._read_postgres(user_id)

    def _redis_key(self, user_id: str) -> str:
        """Return the namespaced Redis key for ``user_id``."""

        return f"{self._key_prefix}:{user_id}"

    def _redis_client(self) -> Optional[Any]:
        """Return a connected Redis client, or None. Never raises."""

        if self._redis is not None:
            return self._redis

        if self._redis_attempted:
            return None

        self._redis_attempted = True

        if self._requested_backend == BACKEND_MEMORY or not self._redis_url:
            return None

        try:
            import redis  # type: ignore
        except ImportError as error:
            LOGGER.info(
                "redis package unavailable (%s), using fallback store",
                error,
            )
            return None

        try:
            client = redis.Redis.from_url(
                self._redis_url,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=REDIS_SOCKET_TIMEOUT,
                decode_responses=True,
            )
            client.ping()
        except Exception as error:  # noqa: BLE001
            LOGGER.info(
                "Redis unavailable at %s (%s), using fallback store",
                self._redis_url,
                error,
            )
            return None

        self._redis = client

        LOGGER.info("State store using Redis at %s", self._redis_url)

        return self._redis

    def _read_redis(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read and decode a Redis entry. Never raises."""

        client = self._redis_client()

        if client is None:
            return None

        try:
            raw = client.get(self._redis_key(user_id))
        except Exception as error:  # noqa: BLE001
            self._log_redis_error(
                f"Redis get failed for user {user_id}: {error}"
            )
            self._redis = None
            self._redis_attempted = True
            return None

        if not raw:
            return None

        return self._decode(raw, user_id)

    def _write_redis(self, user_id: str, payload_text: str) -> bool:
        """Write a Redis entry with TTL. Returns success. Never raises."""

        client = self._redis_client()

        if client is None:
            return False

        try:
            client.setex(
                self._redis_key(user_id),
                self._ttl_seconds,
                payload_text,
            )
        except Exception as error:  # noqa: BLE001
            self._log_redis_error(
                f"Redis setex failed for user {user_id}: {error}"
            )
            self._redis = None
            self._redis_attempted = True
            return False

        return True

    def _delete_redis(self, user_id: str) -> None:
        """Delete a Redis entry, ignoring errors."""

        client = self._redis_client()

        if client is None:
            return

        try:
            client.delete(self._redis_key(user_id))
        except Exception as error:  # noqa: BLE001
            self._log_redis_error(
                f"Redis delete failed for user {user_id}: {error}"
            )

    def _postgres(self) -> Optional[Any]:
        """Return a ready PostgreSQL engine, or None. Never raises."""

        if self._postgres_disabled:
            return None

        if self._postgres_engine is not None:
            return self._postgres_engine

        if self._postgres_attempted:
            return None

        self._postgres_attempted = True

        dsn = (os.getenv("DATABASE_URL") or "").strip()

        if not dsn:
            LOGGER.debug("DATABASE_URL unset, PostgreSQL fallback skipped")
            self._postgres_disabled = True
            return None

        try:
            from sqlalchemy import create_engine, text  # type: ignore
        except ImportError as error:
            LOGGER.info(
                "sqlalchemy unavailable (%s), PostgreSQL fallback skipped",
                error,
            )
            self._postgres_disabled = True
            return None

        try:
            engine = create_engine(
                self._normalise_dsn(dsn),
                pool_pre_ping=True,
                future=True,
            )

            with engine.begin() as connection:
                connection.execute(text(CREATE_TABLE_SQL))
        except Exception as error:  # noqa: BLE001
            LOGGER.info(
                "PostgreSQL fallback unavailable (%s), skipping",
                error,
            )
            self._postgres_disabled = True
            return None

        self._postgres_engine = engine

        LOGGER.info(
            "State store using PostgreSQL fallback table %s",
            POSTGRES_TABLE,
        )

        return self._postgres_engine

    def _read_postgres(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read a PostgreSQL row. Never raises."""

        engine = self._postgres()

        if engine is None:
            return None

        try:
            from sqlalchemy import text  # type: ignore

            with engine.connect() as connection:
                row = connection.execute(
                    text(SELECT_SQL),
                    {"user_id": user_id},
                ).first()
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "PostgreSQL read failed for user %s: %s", user_id, error
            )
            return None

        if row is None:
            return None

        return self._decode(row[0], user_id)

    def _write_postgres(self, user_id: str, payload_text: str) -> bool:
        """Upsert a PostgreSQL row. Returns success. Never raises."""

        engine = self._postgres()

        if engine is None:
            return False

        try:
            from sqlalchemy import text  # type: ignore

            with engine.begin() as connection:
                connection.execute(
                    text(UPSERT_SQL),
                    {"user_id": user_id, "payload": payload_text},
                )
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "PostgreSQL write failed for user %s: %s", user_id, error
            )
            return False

        return True

    def _delete_postgres(self, user_id: str) -> None:
        """Delete a PostgreSQL row, ignoring errors."""

        engine = self._postgres()

        if engine is None:
            return

        try:
            from sqlalchemy import text  # type: ignore

            with engine.begin() as connection:
                connection.execute(
                    text(DELETE_SQL),
                    {"user_id": user_id},
                )
        except Exception as error:  # noqa: BLE001
            LOGGER.warning(
                "PostgreSQL delete failed for user %s: %s", user_id, error
            )

    @staticmethod
    def _normalise_dsn(dsn: str) -> str:
        """Return a synchronous SQLAlchemy DSN."""

        if dsn.startswith("postgresql+asyncpg"):
            return dsn.replace(
                "postgresql+asyncpg", "postgresql+psycopg", 1
            )

        if dsn.startswith("postgresql+psycopg2"):
            return dsn.replace(
                "postgresql+psycopg2", "postgresql+psycopg", 1
            )

        return dsn

    def _decode(
        self,
        raw: Any,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Decode a stored payload, dropping anything malformed."""

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError) as error:
            LOGGER.warning(
                "Dropping malformed state for user %s: %s", user_id, error
            )
            return None

        if not isinstance(decoded, dict):
            LOGGER.warning(
                "Dropping state for user %s: expected dict, got %s",
                user_id,
                type(decoded).__name__,
            )
            return None

        return decoded

    def _log_redis_error(self, message: str) -> None:
        """Log a Redis error once at WARNING, then at DEBUG."""

        if self._redis_error_logged:
            LOGGER.debug(message)
            return

        self._redis_error_logged = True

        LOGGER.warning(
            "%s. Further Redis state errors will be logged at DEBUG. "
            "Falling back to the next store.",
            message,
        )


__all__ = [
    "ReplanningStateManager",
    "DEFAULT_KEY_PREFIX",
    "DEFAULT_TTL_HOURS",
    "BACKEND_REDIS",
    "BACKEND_POSTGRES",
    "BACKEND_MEMORY",
    "BACKEND_DISABLED",
]