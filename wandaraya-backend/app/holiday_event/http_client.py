"""Transparent, bounded HTTP transport shared by governed public-source jobs."""
from __future__ import annotations

import asyncio
from functools import partial

import requests

DEFAULT_USER_AGENT = "WANDARAYA-research/1.0 (+contact: project-owner)"


class RequestsAsyncClient:
    """Async facade over requests with proxy inheritance disabled.

    Calendar Sri Lanka currently returns its published robots file to requests
    while returning an HTTP 403 to httpx from the same container.  This class
    records no cache and does not alter IPs, cookies, or access controls.
    """

    transport_name = "requests"

    def __init__(self, *, timeout_seconds: float = 30):
        self.timeout_seconds = timeout_seconds
        self._session: requests.Session | None = None

    async def __aenter__(self) -> "RequestsAsyncClient":
        self._session = requests.Session()
        self._session.trust_env = False
        return self

    async def __aexit__(self, *_exc_info) -> None:
        if self._session:
            self._session.close()
        self._session = None

    async def get(self, url: str, *, headers: dict[str, str] | None = None):
        if self._session is None:
            raise RuntimeError("RequestsAsyncClient must be used as an async context manager")
        resolved_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
        request = partial(self._session.get, url, headers=resolved_headers, timeout=self.timeout_seconds, allow_redirects=True)
        return await asyncio.to_thread(request)
