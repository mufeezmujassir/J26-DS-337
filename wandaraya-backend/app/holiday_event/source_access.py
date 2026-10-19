"""Explicit source access guard; scheduled jobs never bypass site restrictions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from datetime import datetime
from urllib.parse import urlparse
import httpx
import requests

from .http_client import DEFAULT_USER_AGENT, RequestsAsyncClient


@dataclass(frozen=True)
class SourceAccessResult:
    source_name: str
    url: str
    permitted: bool
    reason: str


@dataclass(frozen=True)
class TermsReview:
    """Human-recorded source terms decision; it is never inferred from robots.txt."""
    reviewed: bool
    automated_collection_permitted: bool
    evidence_reference: str | None = None
    reviewed_at: str | None = None
    request_interval_seconds: float = 3.0
    allowed_detail_path_prefixes: tuple[str, ...] = ()
    authorization_type: str | None = None
    authorization_status: str | None = None
    authorization_evidence: str | None = None
    authorization_scope: str | None = None
    standing_authorization: bool = False
    robots_status: int | None = None
    last_access_check: str | None = None
    access_decision: str | None = None


def load_terms_reviews(path: str | Path | None) -> dict[str, TermsReview]:
    """Load local, non-secret source governance evidence.

    The example configuration is deliberately not sufficient to enable live
    collection.  A real review must state both ``reviewed`` and
    ``automated_collection_permitted`` and carry an evidence reference.
    """
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    sources = payload.get("sources", payload)
    if not isinstance(sources, dict):
        raise ValueError("source policy must contain an object named 'sources'")
    reviews: dict[str, TermsReview] = {}
    for source_name, item in sources.items():
        if not isinstance(item, dict):
            raise ValueError(f"source policy for {source_name!r} must be an object")
        reviews[source_name] = TermsReview(
            reviewed=bool(item.get("terms_reviewed", False)),
            automated_collection_permitted=bool(item.get("automated_collection_permitted", False)),
            evidence_reference=item.get("terms_evidence_reference"),
            reviewed_at=item.get("terms_reviewed_at"),
            request_interval_seconds=max(1.0, float(item.get("request_interval_seconds", 3))),
            allowed_detail_path_prefixes=tuple(
                value for value in item.get("allowed_detail_path_prefixes", [])
                if isinstance(value, str) and value.startswith("/")
            ),
            authorization_type=item.get("authorization_type"),
            authorization_status=item.get("authorization_status"),
            authorization_evidence=item.get("authorization_evidence"),
            authorization_scope=item.get("authorization_scope"),
            standing_authorization=bool(item.get("standing_authorization", False)),
            robots_status=item.get("robots_status") if isinstance(item.get("robots_status"), int) else None,
            last_access_check=item.get("last_access_check"),
            access_decision=item.get("access_decision"),
        )
    return reviews


def _terms_evidence_is_complete(review: TermsReview) -> bool:
    if not review.reviewed or not review.automated_collection_permitted:
        return False
    reference = (review.evidence_reference or "").strip()
    placeholder_markers = ("replace_with", "actual_terms", "written_permission_reference", "todo", "example")
    if not reference or reference.startswith("<") or any(marker in reference.casefold() for marker in placeholder_markers):
        return False
    try:
        timestamp = datetime.fromisoformat((review.reviewed_at or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


def _verbal_source_authorization_is_complete(source_name: str, review: TermsReview) -> bool:
    """Accept only explicitly attested, source-specific, in-scope authorization."""
    evidence = (review.authorization_evidence or "").strip()
    scope = (review.authorization_scope or "").casefold()
    required_scope = "calendar" if source_name == "calendar_sri_lanka" else "event"
    return (
        source_name in {"calendar_sri_lanka", "lanka_events"}
        and review.authorization_type == "verbal_permission"
        and review.authorization_status == "user_attested"
        and review.standing_authorization
        and bool(evidence)
        and required_scope in scope
        and "public" in scope
    )


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


async def runtime_access_check(
    source_name: str,
    url: str,
    client,
    *,
    terms_review: TermsReview | None = None,
) -> dict:
    """Check robots independently from a separately documented terms review."""
    base = check_source_access(source_name, url)
    if base["reason"] != "requires_runtime_robots_and_terms_verification":
        return base
    parsed_target = urlparse(url)
    robots_url = f"{parsed_target.scheme}://{parsed_target.netloc}/robots.txt"
    try:
        response = await client.get(robots_url, headers={"User-Agent": DEFAULT_USER_AGENT})
    except (httpx.HTTPError, requests.RequestException) as exc:
        return {**base, "reason": "ACCESS_UNVERIFIED:robots_fetch_failed", "detail": str(exc), "robots_url": robots_url}
    return evaluate_robots_response(base, response, robots_url, target_url=url, terms_review=terms_review, transport=getattr(client, "transport_name", type(client).__name__))


def _robots_allows_target(robots_text: str, target_url: str) -> bool:
    """Evaluate wildcard robots rules for the intended public target path."""
    target_path = urlparse(target_url).path or "/"
    active_for_wildcard = False
    matching_rules: list[tuple[int, bool]] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key == "user-agent":
            active_for_wildcard = value == "*"
            continue
        if key not in {"allow", "disallow"} or not active_for_wildcard or not value:
            continue
        pattern = value.rstrip("$").replace("*", ".*")
        import re
        if re.match(f"^{pattern}", target_path):
            matching_rules.append((len(value), key == "allow"))
    if not matching_rules:
        return True
    # Longest match wins; Allow wins a same-length tie.
    _, permitted = max(matching_rules, key=lambda item: (item[0], item[1]))
    return permitted


def evaluate_robots_response(base: dict, response, robots_url: str, *, target_url: str | None = None, terms_review: TermsReview | None = None, transport: str | None = None) -> dict:
    """Pure policy evaluator, kept separate so access rules are offline-testable."""
    robots_state: str
    if response.status_code == 404:
        robots_state = "NO_ROBOTS_RULES_FOUND"
    elif response.status_code == 403:
        return {**base, "reason": "ACCESS_BLOCKED:robots_forbidden", "robots_url": robots_url, "robots_status": 403}
    elif response.status_code == 429:
        return {**base, "reason": "ACCESS_BLOCKED:robots_rate_limited", "robots_url": robots_url, "robots_status": 429}
    elif response.status_code != 200:
        return {**base, "reason": "ACCESS_UNVERIFIED:robots_http_error", "robots_url": robots_url, "robots_status": response.status_code}
    else:
        lowered = response.text.lower()
        if not lowered.strip() or "user-agent" not in lowered:
            return {**base, "reason": "ACCESS_UNVERIFIED:robots_invalid_content", "robots_url": robots_url, "robots_status": 200}
        if not _robots_allows_target(response.text, target_url or base["url"]):
            return {**base, "reason": "ACCESS_BLOCKED:robots_target_disallowed", "robots_url": robots_url, "robots_status": 200, "target_url": target_url or base["url"], "transport": transport}
        robots_state = "ROBOTS_RULES_RETRIEVED"

    if terms_review and terms_review.authorization_status == "revoked":
        return {**base, "reason": "ACCESS_BLOCKED:authorization_revoked", "robots_url": robots_url, "robots_status": response.status_code, "target_url": target_url or base["url"], "transport": transport}
    if terms_review and _verbal_source_authorization_is_complete(base["source_name"], terms_review):
        source_label = "CALENDAR" if base["source_name"] == "calendar_sri_lanka" else "EVENT"
        return {
            **base,
            "permitted": True,
            "reason": f"AUTHORIZED_PUBLIC_{source_label}_INGESTION",
            "robots_url": robots_url,
            "robots_status": response.status_code,
            "authorization_type": "verbal_permission",
            "authorization_status": "user_attested",
            "authorization_evidence": terms_review.authorization_evidence,
            "authorization_scope": terms_review.authorization_scope,
            "standing_authorization": True,
            "request_interval_seconds": terms_review.request_interval_seconds,
            "target_url": target_url or base["url"],
            "transport": transport,
        }
    if terms_review is None or not terms_review.reviewed:
        return {**base, "reason": f"{robots_state}:terms_review_required", "robots_url": robots_url, "robots_status": response.status_code, "target_url": target_url or base["url"], "transport": transport}
    if not _terms_evidence_is_complete(terms_review):
        return {**base, "reason": "ACCESS_BLOCKED:terms_evidence_incomplete", "robots_url": robots_url, "robots_status": response.status_code, "target_url": target_url or base["url"], "transport": transport}
    return {
        **base,
        "permitted": True,
        "reason": robots_state,
        "robots_url": robots_url,
        "robots_status": response.status_code,
        "terms_evidence_reference": terms_review.evidence_reference,
        "request_interval_seconds": terms_review.request_interval_seconds,
        "target_url": target_url or base["url"],
        "transport": transport,
    }
