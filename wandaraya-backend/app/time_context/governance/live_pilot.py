"""Bounded live-pilot plans. Network execution is disabled by default."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from enum import StrEnum

from pydantic import BaseModel, Field

from app.time_context.governance.srilanka_tourism import SriLankaTourismPermission, _is_srilanka_travel_url


class LivePilotSettings(BaseModel):
    max_pages: int = Field(default=10, gt=0, le=10)
    max_concurrency: int = Field(default=1, ge=1, le=1)
    min_request_interval_seconds: float = Field(default=3.0, ge=3.0)
    max_retries: int = Field(default=1, ge=0, le=1)
    timeout_seconds: float = Field(default=20.0, gt=0)
    max_response_bytes: int = Field(default=1_000_000, gt=0)
    emergency_stop: bool = False


class ConditionApprovalStatus(StrEnum):
    """Whether a material operating condition was confirmed by the source."""

    UNCONFIRMED = "unconfirmed"
    RESEARCHER_PROPOSED = "researcher_proposed"
    SOURCE_CONFIRMED = "source_confirmed"


class SourceAuthorizationConfiguration(BaseModel):
    """Researcher-completed record required before a bounded live run."""
    permission: SriLankaTourismPermission
    approved_domains: set[str] = Field(default_factory=set)
    exact_urls: list[str] = Field(default_factory=list)
    permitted_content_categories: set[str] = Field(default_factory=set)
    retention_conditions: str | None = None
    attribution_conditions: str | None = None
    request_rate_restrictions: str | None = None
    # Text alone is not evidence that Sri Lanka Tourism agreed to a condition.
    # Defaults fail closed and keep older local configuration files valid.
    retention_conditions_status: ConditionApprovalStatus = ConditionApprovalStatus.UNCONFIRMED
    attribution_conditions_status: ConditionApprovalStatus = ConditionApprovalStatus.UNCONFIRMED
    request_rate_restrictions_status: ConditionApprovalStatus = ConditionApprovalStatus.UNCONFIRMED
    researcher_execution_approved_at: datetime | None = None

    def readiness_errors(self, settings: LivePilotSettings) -> list[str]:
        errors = []
        if not self.permission.automated_fetch_allowed: errors.append("reported_automated_fetch_not_approved")
        if not self.permission.technical_execution_approved or self.researcher_execution_approved_at is None: errors.append("technical_execution_approval_missing")
        if not self.approved_domains: errors.append("approved_domains_missing")
        if not self.exact_urls: errors.append("exact_url_plan_missing")
        if not self.permitted_content_categories: errors.append("permitted_content_categories_missing")
        self._condition_errors(errors, "retention_conditions", self.retention_conditions, self.retention_conditions_status)
        self._condition_errors(errors, "attribution_conditions", self.attribution_conditions, self.attribution_conditions_status)
        self._condition_errors(errors, "request_rate_restrictions", self.request_rate_restrictions, self.request_rate_restrictions_status)
        if settings.emergency_stop: errors.append("emergency_stop_enabled")
        if len(self.exact_urls) > settings.max_pages: errors.append("exact_url_plan_exceeds_page_limit")
        for url in self.exact_urls:
            parsed = urlparse(url)
            if parsed.hostname not in self.approved_domains or not _is_srilanka_travel_url(url): errors.append(f"url_not_approved:{url}")
        return errors

    @staticmethod
    def _condition_errors(
        errors: list[str],
        field_name: str,
        value: str | None,
        status: ConditionApprovalStatus,
    ) -> None:
        if not value:
            errors.append(f"{field_name}_missing")
        elif status is not ConditionApprovalStatus.SOURCE_CONFIRMED:
            errors.append(f"{field_name}_not_source_confirmed")


def load_source_authorization_configuration(path: Path) -> SourceAuthorizationConfiguration:
    """Load a researcher-owned local configuration without supplying defaults.

    JSON and schema failures intentionally propagate; a malformed configuration
    must never silently fall back to an executable configuration.
    """
    return SourceAuthorizationConfiguration.model_validate(json.loads(path.read_text(encoding="utf-8")))


class PilotUrlPlan(BaseModel):
    url: str
    canonical_url: str
    approved: bool
    reason: str


class StagedTourismChange(BaseModel):
    source_url: str
    content_sha256: str
    requested_url: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    redirect_history: list[str] = Field(default_factory=list)
    content_type: str | None = None
    response_size_bytes: int | None = None
    retrieved_at: datetime | None = None
    fetch_success: bool = False
    raw_content: bytes | None = Field(default=None, exclude=True, repr=False)
    persistence_allowed: bool = False
    review_required: bool = True
    production_write_performed: bool = False
    qdrant_write_performed: bool = False


def normalize_pilot_url(value: str) -> str:
    parsed = urlparse(value)
    if not _is_srilanka_travel_url(value):
        raise ValueError("only approved https srilanka.travel URLs are eligible")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", parsed.query, ""))


def build_dry_run(urls: list[str], permission: SriLankaTourismPermission, settings: LivePilotSettings) -> list[PilotUrlPlan]:
    seen: set[str] = set(); plan: list[PilotUrlPlan] = []
    allowed = permission.automated_fetch_allowed and permission.technical_execution_approved and not settings.emergency_stop
    for value in urls:
        try:
            canonical = normalize_pilot_url(value)
        except ValueError:
            plan.append(PilotUrlPlan(url=value, canonical_url="", approved=False, reason="unapproved_domain")); continue
        if canonical in seen:
            plan.append(PilotUrlPlan(url=value, canonical_url=canonical, approved=False, reason="duplicate_url")); continue
        seen.add(canonical)
        plan.append(PilotUrlPlan(url=value, canonical_url=canonical, approved=allowed and len(seen) <= settings.max_pages,
            reason="execution_authorized" if allowed else "technical_execution_not_authorized"))
    return plan


def stage_content(*, source_url: str, content: bytes, permission: SriLankaTourismPermission, requested_url: str | None = None,
                  http_status: int | None = None, content_type: str | None = None, retrieved_at: datetime | None = None) -> StagedTourismChange:
    """Produces review-only metadata; content persistence is never performed here."""
    return StagedTourismChange(source_url=normalize_pilot_url(source_url), content_sha256=sha256(content).hexdigest(),
        requested_url=requested_url or source_url, final_url=normalize_pilot_url(source_url), http_status=http_status,
        content_type=content_type, response_size_bytes=len(content), retrieved_at=retrieved_at, fetch_success=http_status is not None,
        raw_content=content, persistence_allowed=permission.persistent_storage_allowed and permission.technical_execution_approved)


class ControlledSriLankaTourismFetcher:
    """The only live-capable component; callers must validate configuration first."""
    def __init__(self, config: SourceAuthorizationConfiguration, settings: LivePilotSettings, *, client_factory=httpx.AsyncClient) -> None:
        self.config, self.settings, self.client_factory = config, settings, client_factory

    async def fetch_exact_urls(self, *, execute: bool) -> list[StagedTourismChange]:
        errors = self.config.readiness_errors(self.settings)
        if not execute:
            raise PermissionError("live execution requires the explicit execute flag")
        if errors:
            raise PermissionError("live acquisition blocked: " + ", ".join(errors))
        results: list[StagedTourismChange] = []
        async with self.client_factory(timeout=httpx.Timeout(self.settings.timeout_seconds), follow_redirects=False,
            headers={"User-Agent": "WANDARAYA-Tourism-Research/1.0 (academic research; contact configured separately)"}) as client:
            for number, url in enumerate(self.config.exact_urls):
                response = await self._get_with_one_retry(client, url)
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    redirect = urljoin(url, location)
                    if normalize_pilot_url(redirect) not in {normalize_pilot_url(item) for item in self.config.exact_urls}:
                        raise PermissionError("redirect destination is not in the exact approved URL plan")
                    raise PermissionError("redirect requires explicit separate URL review")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xml" not in content_type:
                    raise ValueError("unsupported response content type")
                content = response.content
                if len(content) > self.settings.max_response_bytes:
                    raise ValueError("response exceeds configured size limit")
                results.append(stage_content(source_url=url, content=content, permission=self.config.permission,
                    requested_url=url, http_status=response.status_code, content_type=content_type,
                    retrieved_at=datetime.now(timezone.utc)))
                if number + 1 < len(self.config.exact_urls): await asyncio.sleep(self.settings.min_request_interval_seconds)
        return results

    async def _get_with_one_retry(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = await client.get(url)
                if response.status_code not in {429, 502, 503, 504} or attempt == self.settings.max_retries: return response
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == self.settings.max_retries: raise
            await asyncio.sleep(self.settings.min_request_interval_seconds)
        raise RuntimeError("unreachable retry state")
