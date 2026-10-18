"""Polite, bounded request support for Wikimedia-compatible API connectors."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MediaWikiApiClient:
    """Per-host pacing and bounded retries; it never treats an error as content."""

    _locks: dict[str, asyncio.Lock] = {}
    _next_request_at: dict[str, float] = {}

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        min_request_interval_seconds: float = 1.25,
        max_attempts: int = 3,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.min_request_interval_seconds = min_request_interval_seconds
        self.max_attempts = max_attempts
        self.client_factory = client_factory
        contact = os.getenv("WIKIMEDIA_CONTACT_EMAIL", "").strip()
        self.headers = {
            "User-Agent": (
                f"WANDARAYA-Tourism-Research/1.0 ({contact})"
                if contact
                else "WANDARAYA-Tourism-Research/1.0 (academic tourism research)"
            ),
            "Accept": "application/json",
        }

    @property
    def host_key(self) -> str:
        return self.base_url.split("/", 3)[2]

    async def _wait_for_turn(self) -> None:
        lock = self._locks.setdefault(self.host_key, asyncio.Lock())
        async with lock:
            delay = self._next_request_at.get(self.host_key, 0.0) - monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at[self.host_key] = monotonic() + self.min_request_interval_seconds

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return min(max(float(value), 0.0), 60.0)
            except ValueError:
                try:
                    return min(max((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds(), 0.0), 60.0)
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(float(2 ** attempt), 30.0)

    async def get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch JSON, retrying only transient failures and finally raising context."""
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            await self._wait_for_turn()
            try:
                async with self.client_factory(timeout=self.timeout, headers=self.headers) as client:
                    response = await client.get(self.base_url, params=params)
                if response.status_code not in {429, 502, 503, 504}:
                    response.raise_for_status()
                    return response.json()
                last_error = httpx.HTTPStatusError(
                    f"Transient Wikimedia API response {response.status_code}", request=response.request, response=response
                )
                if attempt + 1 < self.max_attempts:
                    delay = self._retry_after_seconds(response, attempt + 1)
                    logger.warning("Wikimedia request throttled/transient | host=%s status=%s retry_in=%.1fs attempt=%s/%s",
                        self.host_key, response.status_code, delay, attempt + 1, self.max_attempts)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    delay = min(float(2 ** (attempt + 1)), 30.0)
                    logger.warning("Wikimedia network error | host=%s retry_in=%.1fs attempt=%s/%s error=%s",
                        self.host_key, delay, attempt + 1, self.max_attempts, exc)
                    await asyncio.sleep(delay)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Wikimedia request ended without a response")
