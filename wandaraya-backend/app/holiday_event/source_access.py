"""Explicit source access guard; scheduled jobs never bypass site restrictions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceAccessResult:
    source_name: str
    url: str
    permitted: bool
    reason: str


APPROVED = {
    "calendar_sri_lanka": "calendarsrilanka.com",
    "lanka_events": "lankaevents.lk",
    "third_source_placeholder": None,
}


def check_source_access(source_name: str, url: str) -> dict:
    host = urlparse(url).hostname
    approved_host = APPROVED.get(source_name)
    if not approved_host:
        return asdict(SourceAccessResult(source_name, url, False, "source_not_configured"))
    if urlparse(url).scheme != "https" or host not in {approved_host, f"www.{approved_host}"}:
        return asdict(SourceAccessResult(source_name, url, False, "unapproved_url"))
    # robots/terms must be checked at execution time; an HTTP response alone is insufficient.
    return asdict(SourceAccessResult(source_name, url, False, "requires_runtime_robots_and_terms_verification"))
