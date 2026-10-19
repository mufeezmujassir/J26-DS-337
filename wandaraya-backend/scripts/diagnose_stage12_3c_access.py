"""Reproduce Stage 12.3C source-access transport results without DB writes."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import requests

from app.holiday_event.http_client import DEFAULT_USER_AGENT, RequestsAsyncClient
from app.holiday_event.source_access import check_source_access, load_terms_reviews, runtime_access_check


def summarize(response, client: str) -> dict:
    body = response.text.encode("utf-8", errors="replace")
    return {
        "client": client,
        "status": response.status_code,
        "final_url": str(response.url),
        "redirect_statuses": [item.status_code for item in response.history],
        "server": response.headers.get("server"),
        "content_type": response.headers.get("content-type"),
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }


async def main() -> None:
    robots_url = "https://calendarsrilanka.com/robots.txt"
    session = requests.Session()
    session.trust_env = False
    try:
        direct = await asyncio.to_thread(session.get, robots_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=30, allow_redirects=True)
    finally:
        session.close()
    httpx_response = httpx.get(robots_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=30, follow_redirects=True, trust_env=False)
    reviews = load_terms_reviews("config/holiday_event_source_policy.local.json")
    async with RequestsAsyncClient(timeout_seconds=30) as client:
        policy_result = await runtime_access_check("calendar_sri_lanka", "https://calendarsrilanka.com/", client, terms_review=reviews.get("calendar_sri_lanka"))
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": "https://calendarsrilanka.com/",
        "robots_url": robots_url,
        "transport_comparison": [summarize(direct, "requests"), summarize(httpx_response, "httpx")],
        "policy_result": policy_result,
        "diagnosis": "requests received the robots policy while httpx received a source HTTP 403; the governed checker now uses requests with the declared WANDARAYA user-agent and proxy inheritance disabled.",
        "database_writes": False,
        "qdrant_writes": False,
    }
    output = Path("data/reports/stage12_3c_access_diagnostic.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
