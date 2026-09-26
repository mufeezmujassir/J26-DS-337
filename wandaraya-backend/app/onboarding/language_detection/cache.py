"""Redis-backed result cache for language detection."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from app.onboarding.language_detection.utils import build_cache_key

LOGGER = logging.getLogger(__name__)

BACKEND_DISABLED = "disabled"
BACKEND_REDIS = "redis"
BACKEND_MEMORY = "memory"

DEFAULT_TTL_SECONDS = 86400
DEFAULT_KEY_PREFIX = "langdetect"
DEFAULT_MAX_MEMORY_ENTRIES = 10000
DEFAULT_SOCKET_TIMEOUT = 1.0


class LanguageDetectionCache:
    """Cache of detection results with a Redis or in-memory backend."""

    def __init__(
        self,
        enabled: bool = True,
        redis_url: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        socket_timeout: float = DEFAULT_SOCKET_TIMEOUT,
        max_memory_entries: int = DEFAULT_MAX_MEMORY_ENTRIES,
    ) -> None:
        """Create the cache and attempt to connect to Redis."""

        self.enabled = bool(enabled)
        self.ttl_seconds = int(ttl_seconds)
        self.key_prefix = key_prefix
        self.max_memory_entries = int(max_memory_entries)
        self.socket_timeout = float(socket_timeout)

        self._redis: Any = None
        self._memory: "OrderedDict[str, tuple]" = OrderedDict()
        self._redis_error_logged = False

        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._errors = 0

        if not self.enabled:
            LOGGER.info("Language detection cache is disabled")

            return

        if not self._connect_redis(redis_url):
            LOGGER.info(
                "Redis unavailable, using in-memory detection cache "
                "(max %d entries, ttl %ds)",
                self.max_memory_entries,
                self.ttl_seconds,
            )

    @property
    def backend(self) -> str:
        """Active backend: ``"redis"``, ``"memory"`` or ``"disabled"``."""

        if not self.enabled:
            return BACKEND_DISABLED

        if self._redis is not None:
            return BACKEND_REDIS

        return BACKEND_MEMORY

    @property
    def is_redis(self) -> bool:
        """True when Redis is the active backend."""

        return self.enabled and self._redis is not None

    def get(self, text: str) -> Optional[Dict[str, Any]]:
        """Return the cached result for the text, or None on a miss."""

        if not self.enabled or not isinstance(text, str) or not text:
            return None

        key = self._make_key(text)

        if self._redis is not None:
            cached = self._get_from_redis(key)
        else:
            cached = self._get_from_memory(key)

        if cached is None:
            self._misses += 1

            return None

        self._hits += 1

        LOGGER.debug(
            "Language detection cache hit for key %s", key
        )

        return cached

    def set(
        self,
        text: str,
        result: Dict[str, Any],
    ) -> None:
        """Store a detection result for the text."""

        if not self.enabled or not isinstance(text, str) or not text:
            return

        if not isinstance(result, dict):
            LOGGER.warning(
                "Refusing to cache a non-dict result of type %s for "
                "key %s",
                type(result).__name__,
                self._make_key(text),
            )

            return

        key = self._make_key(text)

        if self._redis is not None:
            self._set_in_redis(key, result)
        else:
            self._set_in_memory(key, result)

        self._writes += 1

    def delete(self, text: str) -> bool:
        """Remove one entry. Returns True if something was removed."""

        if not self.enabled or not isinstance(text, str) or not text:
            return False

        key = self._make_key(text)

        if self._redis is not None:
            try:
                return bool(self._redis.delete(key))
            except Exception as error:  # noqa: BLE001
                self._errors += 1
                LOGGER.warning(
                    "Redis delete failed for key %s: %s", key, error
                )

                return False

        removed = self._purge_memory_key(key)

        return removed is not None

    def clear(self) -> int:
        """Drop every entry owned by this cache."""

        if not self.enabled:
            return 0

        if self._redis is not None:
            try:
                pattern = f"{self.key_prefix}:*"
                keys = list(self._redis.scan_iter(match=pattern))
                deleted = (
                    self._redis.delete(*keys) if keys else 0
                )

                LOGGER.info(
                    "Cleared %d language detection keys from Redis",
                    deleted,
                )

                return int(deleted)
            except Exception as error:  # noqa: BLE001
                self._errors += 1
                LOGGER.warning(
                    "Redis clear failed for pattern %s: %s",
                    f"{self.key_prefix}:*",
                    error,
                )

                return 0

        count = len(self._memory)
        self._memory.clear()

        LOGGER.info(
            "Cleared %d language detection keys from memory cache",
            count,
        )

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Return counters and configuration for monitoring."""

        return {
            "backend": self.backend,
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
            "key_prefix": self.key_prefix,
            "hits": self._hits,
            "misses": self._misses,
            "writes": self._writes,
            "errors": self._errors,
            "hit_rate": (
                round(self._hits / (self._hits + self._misses), 4)
                if (self._hits + self._misses) > 0
                else 0.0
            ),
            "memory_entries": len(self._memory),
            "max_memory_entries": self.max_memory_entries,
        }

    def close(self) -> None:
        """Release the Redis connection and clear local state."""

        if self._redis is not None:
            try:
                self._redis.close()
            except Exception as error:  # noqa: BLE001
                LOGGER.debug(
                    "Error closing Redis connection: %s", error
                )

            self._redis = None

        self._memory.clear()

    def _connect_redis(self, redis_url: Optional[str]) -> bool:
        """Try to open a Redis connection. Never raises."""

        url = redis_url or self._redis_url_from_env()

        if not url:
            LOGGER.debug(
                "No Redis URL configured, skipping Redis connection"
            )

            return False

        try:
            import redis  # type: ignore
        except ImportError as error:
            LOGGER.debug(
                "redis package not installed, using in-memory cache: %s",
                error,
            )

            return False

        try:
            client = redis.Redis.from_url(
                url,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_timeout,
                decode_responses=True,
            )
            client.ping()
        except Exception as error:  # noqa: BLE001
            LOGGER.info(
                "Redis connection to %s failed (%s), using in-memory "
                "cache instead",
                url,
                error,
            )

            return False

        self._redis = client

        LOGGER.info(
            "Language detection cache using Redis at %s (ttl %ds)",
            url,
            self.ttl_seconds,
        )

        return True

    @staticmethod
    def _redis_url_from_env() -> Optional[str]:
        """Return the Redis URL from the environment, if set."""

        return os.getenv("REDIS_URL") or None

    def _make_key(self, text: str) -> str:
        """Return the cache key ``"{key_prefix}:{hash_of_text}"``."""

        return build_cache_key(text, prefix=self.key_prefix)

    def _get_from_redis(self, key: str) -> Optional[Dict[str, Any]]:
        """Read and decode an entry from Redis. Never raises."""

        try:
            raw = self._redis.get(key)
        except Exception as error:  # noqa: BLE001
            self._errors += 1
            self._log_redis_error_once(
                f"Redis get failed for key {key}: {error}"
            )

            return None

        if not raw:
            return None

        return self._decode(raw, key)

    def _set_in_redis(
        self,
        key: str,
        result: Dict[str, Any],
    ) -> None:
        """Serialise and store an entry in Redis. Never raises."""

        try:
            payload = json.dumps(result, ensure_ascii=False)
            self._redis.setex(
                key,
                self.ttl_seconds,
                payload,
            )
        except Exception as error:  # noqa: BLE001
            self._errors += 1
            self._log_redis_error_once(
                f"Redis setex failed for key {key}: {error}"
            )

    def _get_from_memory(self, key: str) -> Optional[Dict[str, Any]]:
        """Read an entry from the in-memory LRU, honouring expiry."""

        entry = self._memory.get(key)

        if entry is None:
            return None

        expires_at, value = entry

        if expires_at <= time.time():
            self._memory.pop(key, None)

            return None

        if not isinstance(value, dict):
            LOGGER.warning(
                "Dropping malformed in-memory cache payload for key %s: "
                "expected dict, got %s",
                key,
                type(value).__name__,
            )
            self._memory.pop(key, None)

            return None

        self._memory.move_to_end(key)

        return value

    def _set_in_memory(
        self,
        key: str,
        result: Dict[str, Any],
    ) -> None:
        """Store an entry in the in-memory LRU, evicting if full."""

        self._memory[key] = (
            time.time() + self.ttl_seconds,
            dict(result),
        )
        self._memory.move_to_end(key)

        while len(self._memory) > self.max_memory_entries:
            evicted_key, _ = self._memory.popitem(last=False)
            LOGGER.debug(
                "Evicted detection cache entry %s (LRU overflow)",
                evicted_key,
            )

    def _purge_memory_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Remove an in-memory entry, returning it when present."""

        entry = self._memory.pop(key, None)

        return entry[1] if entry else None

    @staticmethod
    def _decode(raw: Any, key: str) -> Optional[Dict[str, Any]]:
        """Decode a cached payload, dropping anything malformed."""

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError) as error:
            LOGGER.warning(
                "Dropping malformed cache payload for key %s: %s",
                key,
                error,
            )

            return None

        if not isinstance(decoded, dict):
            LOGGER.warning(
                "Dropping cache payload for key %s: expected dict, got %s",
                key,
                type(decoded).__name__,
            )

            return None

        return decoded

    def _log_redis_error_once(self, message: str) -> None:
        """Log a Redis error at WARNING once, then at DEBUG."""

        if self._redis_error_logged:
            LOGGER.debug(message)

            return

        self._redis_error_logged = True
        LOGGER.warning(
            "%s. Further Redis cache errors will be logged at DEBUG. "
            "Detection is unaffected.",
            message,
        )