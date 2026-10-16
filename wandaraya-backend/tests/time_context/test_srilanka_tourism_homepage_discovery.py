import json
import asyncio

import httpx
import pytest

from app.time_context.governance.homepage_discovery import extract_and_discover_homepage, normalize_discovered_url, write_gate4_review_artifacts
from app.time_context.governance.live_pilot import ConditionApprovalStatus, ControlledSriLankaTourismFetcher, LivePilotSettings, SourceAuthorizationConfiguration
from app.time_context.governance.srilanka_tourism import SriLankaTourismPermission


def test_extracts_homepage_metadata_and_review_only_internal_inventory(tmp_path):
    html = """<html><head><title>Discover Sri Lanka</title><meta name='description' content='Plan a trip'>
    <script type='application/ld+json'>{\"@type\": \"WebSite\"}</script></head><body><nav>
    <a href='/destinations/'>Destinations</a><a href='/destinations#top'>Destinations</a></nav>
    <h1>Welcome</h1><h2>Explore</h2><a href='https://example.com'>External</a>
    <a href='/events/'>Events</a></body></html>"""
    result = extract_and_discover_homepage(source_url="https://srilanka.travel/", html=html)
    assert result.extraction.page_title == "Discover Sri Lanka"
    assert result.extraction.meta_description == "Plan a trip"
    assert result.extraction.main_headings == ["Welcome", "Explore"]
    assert result.external_link_count == 1 and result.duplicate_internal_link_count == 1
    assert result.category_distribution == {"destinations": 1, "events": 1}
    pilot, inventory = write_gate4_review_artifacts(result=result, pilot_metadata={"fetch_success": True}, reports_dir=tmp_path)
    assert json.loads(pilot.read_text())["status"] == "review_required"
    assert json.loads(inventory.read_text())["status"] == "review_only_not_fetch_authorization"


def test_missing_metadata_malformed_html_and_external_url_are_fail_closed():
    result = extract_and_discover_homepage(source_url="https://srilanka.travel/", html="<a href='/activities'>Things to do")
    assert "Page title is absent." in result.extraction.parsing_warnings
    assert "Meta description is absent." in result.extraction.parsing_warnings
    assert result.category_distribution == {"activities": 1}
    try:
        normalize_discovered_url("https://example.com/x", base_url="https://srilanka.travel/")
    except ValueError as error:
        assert "outside the approved" in str(error)
    else:
        raise AssertionError("external URL must be rejected")


def _ready_config() -> SourceAuthorizationConfiguration:
    return SourceAuthorizationConfiguration(
        permission=SriLankaTourismPermission(automated_fetch_allowed=True, technical_execution_approved=True),
        approved_domains={"srilanka.travel"},
        exact_urls=["https://srilanka.travel/"],
        permitted_content_categories={"destination"},
        retention_conditions="confirmed", retention_conditions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        attribution_conditions="confirmed", attribution_conditions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        request_rate_restrictions="confirmed", request_rate_restrictions_status=ConditionApprovalStatus.SOURCE_CONFIRMED,
        researcher_execution_approved_at="2026-10-14T12:30:00+05:30",
    )


class _MockClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _url):
        return self.response


def test_redirect_destination_is_rejected_without_following_it():
    class RedirectResponse:
        is_redirect = True
        status_code = 302
        headers = {"location": "/destinations/"}

    fetcher = ControlledSriLankaTourismFetcher(
        _ready_config(), LivePilotSettings(), client_factory=lambda **_kwargs: _MockClient(RedirectResponse())
    )
    with pytest.raises(PermissionError, match="redirect destination is not in the exact approved URL plan"):
        asyncio.run(fetcher.fetch_exact_urls(execute=True))


def test_failed_http_response_is_raised_and_never_staged():
    class FailedResponse:
        is_redirect = False
        status_code = 500
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            request = httpx.Request("GET", "https://srilanka.travel/")
            raise httpx.HTTPStatusError("server error", request=request, response=httpx.Response(500, request=request))

    fetcher = ControlledSriLankaTourismFetcher(
        _ready_config(), LivePilotSettings(), client_factory=lambda **_kwargs: _MockClient(FailedResponse())
    )
    with pytest.raises(httpx.HTTPStatusError, match="server error"):
        asyncio.run(fetcher.fetch_exact_urls(execute=True))
